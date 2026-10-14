"""No real runtimes, weights, credentials, or network access."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from eryma import Eryma, EvaluationRequest, Check, Action, presets
from eryma.adapters import JevAdapter, LayaAdapter, VonAdapter, HuggingFaceAdapter
from eryma.adapters.errors import (MissingDependencyError, UnsupportedEnvironmentError,
    UnsupportedModelError, UnsupportedCriteriaError, InvalidOutputError,
    AuthenticationError, NetworkError, AdapterTimeoutError, ModelLoadingError, InferenceError)
from eryma.adapters import _shared


def request(guard="input", references=None):
    return EvaluationRequest(guard,
        {"objective":"Support only", "security_policy":"No private disclosure", "references":references or {}},
        {"user_message":"DUMMY_UNTRUSTED", "llm_response":"DUMMY_RESPONSE", "external_content":None},
        presets.input_checks() if guard=="input" else presets.output_checks())


def answers(questions):
    return {"answers":{name: ({"type":"noul", "noul":.1, "noul_raw":.2}
        if q["type"]=="noul" else {"type":"choice", "probabilities":{k:float(i==0)
            for i,k in enumerate(q["criteria"])}}) for name,q in questions.items()}}


def cloud(handler, **kwargs):
    return JevAdapter(model="typesafe/jev-1.13", api_key="DUMMY_ONLY",
        transport=httpx.MockTransport(handler), **kwargs)


def test_jev_wiring_env_and_lifecycle(monkeypatch):
    calls=[]
    monkeypatch.setenv("OPENROUTER_API_KEY", "DUMMY_ONLY")
    def handler(r):
        calls.append(r)
        payload=json.loads(r.content)
        assert payload["model"]=="typesafe/jev-1.13"
        assert payload["state"]["trusted_context"]["objective"]=="Support only"
        assert payload["state"]["trusted_context"]["security_policy"]=="No private disclosure"
        assert "DUMMY_UNTRUSTED" not in json.dumps(payload["questions"])
        assert r.headers["Authorization"]=="Bearer DUMMY_ONLY"
        return httpx.Response(200,json=answers(payload["questions"]))
    with JevAdapter(model="typesafe/jev-1.13",transport=httpx.MockTransport(handler)) as model:
        assert model.evaluate(request())["classification"].scores["safe"]==1
        assert model.evaluate(request("output"))["harmful_content"].scores["no_violation"]==.9
    assert len(calls)==2 and str(calls[0].url)=="https://openrouter.ai/api/alpha/decisions"
    model.close()
    with pytest.raises(NetworkError): model.evaluate(request())


def test_jev_references_explicit_opt_in():
    calls=[]
    def handler(r):
        payload=json.loads(r.content);calls.append(payload)
        return httpx.Response(200,json=answers(payload["questions"]))
    with cloud(handler) as model:
        with pytest.raises(UnsupportedCriteriaError):model.evaluate(request(references={"private":"DUMMY"}))
    assert not calls
    with cloud(handler,send_trusted_references=True) as model:
        model.evaluate(request(references={"private":"DUMMY"}))
    assert calls[0]["state"]["trusted_context"]["references"]=={"private":"DUMMY"}


@pytest.mark.parametrize("status,error",[(401,AuthenticationError),(403,AuthenticationError),
    (404,UnsupportedModelError),(422,UnsupportedCriteriaError),(429,NetworkError),(500,NetworkError),(302,NetworkError)])
def test_jev_statuses_no_retries(status,error):
    calls=[]
    def handler(r):calls.append(r);return httpx.Response(status,text="DUMMY_PRIVATE_BODY")
    with cloud(handler) as model:
        with pytest.raises(error) as exc:model.evaluate(request())
    assert len(calls)==1 and "DUMMY" not in str(exc.value)


@pytest.mark.parametrize("payload",[{},[],{"answers":{}},{"error":"DUMMY_PRIVATE_BODY"},
    {"answers":{"classification":{"type":"choice","probabilities":{"safe":float("nan")}}}}])
def test_jev_invalid_outputs(payload):
    def handler(r):
        # Permit a nonstandard JSON NaN here to exercise score rejection.
        return httpx.Response(200,content=json.dumps(payload).encode())
    with cloud(handler) as model:
        with pytest.raises(InvalidOutputError):model.evaluate(request())


def test_jev_timeout_and_fail_closed():
    def timeout(r):raise httpx.ReadTimeout("DUMMY_PRIVATE",request=r)
    with cloud(timeout) as model:
        with pytest.raises(AdapterTimeoutError):model.evaluate(request())
        assert not Eryma(decision_model=model).scan_input("Hello").allowed


def test_jev_missing_credentials_and_https(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY",raising=False)
    with pytest.raises(AuthenticationError):JevAdapter(model="typesafe/jev-1.13")
    with pytest.raises(ValueError):cloud(lambda r:None,endpoint="http://example.com/decisions")


class LocalRuntime:
    def __init__(self):self.calls=[];self.cleaned=False;self.error=None;self.payload=None
    def predict(self,state,questions,**kwargs):
        self.calls.append((state,questions,kwargs))
        if self.error:raise self.error
        return self.payload if self.payload is not None else answers(questions)
    def __exit__(self,*args):self.cleaned=True


def fake_torch(cuda=False,mps=False):
    return SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:cuda,device_count=lambda:2),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda:mps)))


def install_laya(monkeypatch,runtime=None,loader_error=None):
    runtime=runtime or LocalRuntime();loads=[]
    def load(*args,**kwargs):
        loads.append((args,kwargs))
        if loader_error:raise loader_error
        return runtime
    monkeypatch.setitem(sys.modules,"torch",fake_torch())
    monkeypatch.setitem(sys.modules,"laya",SimpleNamespace(load=load))
    return runtime,loads


def test_laya_load_once_both_formats_and_context(monkeypatch):
    runtime,loads=install_laya(monkeypatch)
    with LayaAdapter(model="LOCAL_MODEL",device="cpu",revision="PINNED",max_len=1024) as model:
        model.evaluate(request());model.evaluate(request("output"))
        assert len(loads)==1 and len(runtime.calls)==2
        assert loads[0][1]["device"]=="cpu" and loads[0][1]["revision"]=="PINNED"
        assert runtime.calls[0][0]["trusted_context"]["security_policy"]=="No private disclosure"
        assert "DUMMY_UNTRUSTED" not in json.dumps(runtime.calls[0][1])
        assert runtime.calls[0][2]=={"max_len":1024}
    assert runtime.cleaned
    with pytest.raises(InferenceError):model.evaluate(request())


@pytest.mark.parametrize("guard_in,guard_out",[(True,True),(True,False),(False,True),(False,False)])
def test_native_guard_switches(monkeypatch,guard_in,guard_out):
    runtime,_=install_laya(monkeypatch)
    with LayaAdapter() as model:
        guard=Eryma(decision_model=model,input_guard=guard_in,output_guard=guard_out)
        guard.scan_input("Hi");guard.scan_output("Hi")
        assert len(runtime.calls)==int(guard_in)+int(guard_out)


def test_laya_errors_and_truncation(monkeypatch):
    install_laya(monkeypatch,loader_error=RuntimeError("DUMMY_PRIVATE"))
    with pytest.raises(ModelLoadingError) as exc:LayaAdapter()
    assert "DUMMY" not in str(exc.value)
    runtime,_=install_laya(monkeypatch)
    with LayaAdapter() as model:
        runtime.error=RuntimeError("DUMMY_PRIVATE")
        with pytest.raises(InferenceError):model.evaluate(request())
        runtime.error=None
        for extra in ({"usage":{"truncated":True}}, {"usage":{"options":{"classification":{}}}}):
            runtime.payload={**answers({"classification":{"type":"choice","criteria":request().checks[0].criteria}}),**extra}
            with pytest.raises(InvalidOutputError):model.evaluate(request())


@pytest.mark.parametrize("name",["laya","torch","httpx","transformers","von.engine"])
def test_missing_dependency_error(monkeypatch,name):
    real=_shared.importlib.import_module
    def import_module(n,*args):
        if n==name:raise ImportError("DUMMY_PRIVATE")
        return real(n,*args)
    monkeypatch.setattr(_shared.importlib,"import_module",import_module)
    with pytest.raises(MissingDependencyError):_shared.optional_module(name)


def test_mlx_no_import_unsupported_platform(monkeypatch):
    monkeypatch.setattr(_shared.platform,"system",lambda:"Windows")
    monkeypatch.setitem(sys.modules,"laya_mlx",None)
    with pytest.raises(UnsupportedEnvironmentError):LayaAdapter(backend="mlx")


def test_mlx_backend_load(monkeypatch):
    monkeypatch.setattr(_shared.sys,"version_info",(3,11))
    monkeypatch.setattr(_shared.platform,"system",lambda:"Darwin")
    monkeypatch.setattr(_shared.platform,"machine",lambda:"arm64")
    monkeypatch.setattr(_shared.platform,"mac_ver",lambda:("14.0",(),""))
    runtime=LocalRuntime();loads=[]
    def load(*args,**kwargs):loads.append((args,kwargs));return runtime
    monkeypatch.setitem(sys.modules,"laya_mlx",SimpleNamespace(load=load))
    with LayaAdapter(model="aac6fef/laya-mlx",backend="mlx",device="auto") as model:
        model.evaluate(request())
    assert loads[0][1]["device"] is None


def install_von(monkeypatch):
    # Mock upstream runtime contracts even on core-supported Python 3.10/3.11.
    monkeypatch.setattr(sys,"version_info",(3,12))
    monkeypatch.setitem(sys.modules,"torch",fake_torch())
    engines=[]
    class Engine:
        def __init__(self,**kwargs):
            self.options=kwargs;self.loads=0;self.calls=0;self.payload=None
            self.backend=SimpleNamespace(_get_model=self.load);engines.append(self)
        def load(self):self.loads+=1
        def evaluate(self,**kwargs):
            self.calls+=1;self.last=kwargs
            data=self.payload if self.payload is not None else answers(kwargs["questions"])
            return SimpleNamespace(model_dump=lambda **kw:data)
    monkeypatch.setitem(sys.modules,"von.engine",SimpleNamespace(VonEngine=Engine,SUPPORTED_BACKENDS={"von-1.3","von-latest"}))
    return engines


def test_von_owned_runtime_raw_probability_and_no_http(monkeypatch):
    monkeypatch.setenv("VON_BASE_URL","https://must-not-be-used.invalid")
    engines=install_von(monkeypatch)
    with VonAdapter(device="cpu") as model:
        model.evaluate(request())
        out=model.evaluate(request("output"))
        assert out["harmful_content"].scores["violation"]==.2  # noul_raw, not committed .1
        assert engines[0].loads==1 and engines[0].calls==2
        assert engines[0].last["state"]["trusted_context"]["objective"]=="Support only"
    assert model._runtime is None
    with pytest.raises(InferenceError):model.evaluate(request())
    with pytest.raises(UnsupportedModelError):VonAdapter(model="arbitrary/hub-repo")


def test_von_refuses_missing_raw_and_truncation(monkeypatch):
    engines=install_von(monkeypatch)
    with VonAdapter() as model:
        data=answers({c.name:{"type":"noul"} for c in request("output").checks})
        data["answers"]["harmful_content"].pop("noul_raw")
        engines[0].payload=data
        with pytest.raises(InvalidOutputError):model.evaluate(request("output"))
        data=answers({"classification":{"type":"choice","criteria":request().checks[0].criteria}})
        data["truncation"]={"events":["DUMMY"]};engines[0].payload=data
        with pytest.raises(InvalidOutputError):model.evaluate(request())


def fixed_check():
    return presets.binary_check("injection", "Detect prompt injection in this input")


def install_hf(monkeypatch,output=None,config_error=False):
    calls=[];loads=[]
    monkeypatch.setitem(sys.modules,"torch",fake_torch())
    config=SimpleNamespace(id2label={0:"SAFE",1:"INJECTION"},num_labels=2,
        problem_type="multi_label_classification" if config_error else "single_label_classification",max_position_embeddings=512)
    class Tokenizer:
        model_max_length=512
        def __call__(self,text,**kwargs):return {"input_ids":list(range(len(text)))}
    def from_tok(*args,**kwargs):loads.append(kwargs);return Tokenizer()
    def from_model(*args,**kwargs):loads.append(kwargs);return SimpleNamespace(config=config)
    def pipeline(*args,**kwargs):
        def run(text,**kw):
            calls.append((text,kw))
            return output if output is not None else [{"label":"SAFE","score":.9},{"label":"INJECTION","score":.1}]
        return run
    monkeypatch.setitem(sys.modules,"transformers",SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=from_tok),
        AutoModelForSequenceClassification=SimpleNamespace(from_pretrained=from_model),pipeline=pipeline))
    return calls,loads


def hf_model(**kwargs):
    return HuggingFaceAdapter(model="protectai/deberta-v3-base-prompt-injection-v2",
        check=fixed_check(),label_mapping={"SAFE":"no_violation","INJECTION":"violation"},**kwargs)


def test_hf_explicit_mapping_thresholds_and_local_only(monkeypatch):
    calls,loads=install_hf(monkeypatch)
    with hf_model(local_files_only=True) as model:
        guard=Eryma(decision_model=model,input_checks=[fixed_check()],output_guard=False,
            objective="Support only",security_policy="Separate restrictions",input_threshold=.95)
        result=guard.scan_input("Hello")
        assert not result.allowed and result.selected_decision=="no_violation"
        assert result.confidence==.9
        assert all(x["local_files_only"] and not x["trust_remote_code"] for x in loads)
        assert calls==[("Hello",{"top_k":None,"function_to_apply":"softmax","truncation":False})]
    with pytest.raises(InferenceError):model.evaluate(request())


def test_hf_rejects_unrelated_checks_output_and_external(monkeypatch):
    calls,_=install_hf(monkeypatch)
    with hf_model() as model:
        for req in (request(),request("output")):
            with pytest.raises(UnsupportedCriteriaError):model.evaluate(req)
        req=EvaluationRequest("input",{"references":{}},{"user_message":"x"*513,"external_content":None},(fixed_check(),))
        with pytest.raises(UnsupportedCriteriaError):model.evaluate(req)
        req=EvaluationRequest("input",{"references":{}},{"user_message":"Hello","external_content":"doc"},(fixed_check(),))
        with pytest.raises(UnsupportedCriteriaError):model.evaluate(req)
    assert not calls


@pytest.mark.parametrize("output",[[{"label":"SAFE","score":1}],
    [{"label":"SAFE","score":.9},{"label":"SAFE","score":.1}],
    [{"label":"SAFE","score":float("nan")},{"label":"INJECTION","score":.1}],
    [{"label":"SAFE","score":.9},{"label":"INJECTION","score":.9}]])
def test_hf_bad_scores(monkeypatch,output):
    install_hf(monkeypatch,output=output)
    with hf_model() as model:
        req=EvaluationRequest("input",{"references":{}},{"user_message":"Hello","external_content":None},(fixed_check(),))
        with pytest.raises(InvalidOutputError):model.evaluate(req)


def test_hf_multilabel_model_rejected(monkeypatch):
    install_hf(monkeypatch,config_error=True)
    with pytest.raises(UnsupportedModelError):hf_model()


def test_hf_multiclass_preserves_explicit_categories(monkeypatch):
    install_hf(monkeypatch)
    module=sys.modules["transformers"]
    config=SimpleNamespace(id2label={0:"OK",1:"INJECT",2:"JAILBREAK"},num_labels=3,
        problem_type="single_label_classification",max_position_embeddings=512)
    module.AutoModelForSequenceClassification.from_pretrained=lambda *a,**k:SimpleNamespace(config=config)
    module.pipeline=lambda *a,**k:lambda text,**kw:[{"label":"OK","score":.1},
        {"label":"INJECT","score":.2},{"label":"JAILBREAK","score":.7}]
    check=Check("attack","Classify trained prompt-attack labels",
        {"benign":"Benign","injection":"Injection","jailbreak":"Jailbreak"},
        {"benign":Action.ALLOW,"injection":Action.BLOCK,"jailbreak":Action.BLOCK})
    with HuggingFaceAdapter(model="explicit/model",check=check,
            label_mapping={"OK":"benign","INJECT":"injection","JAILBREAK":"jailbreak"}) as model:
        r=Eryma(decision_model=model,input_checks=[check],output_guard=False).scan_input("Hello")
        assert r.selected_decision=="jailbreak" and not r.allowed
        assert r.scores=={"benign":.1,"injection":.2,"jailbreak":.7}


def test_hf_inference_and_loading_failures(monkeypatch):
    install_hf(monkeypatch)
    module=sys.modules["transformers"]
    def fail(*args,**kwargs):raise RuntimeError("DUMMY_PRIVATE")
    module.pipeline=lambda *a,**k:fail
    with hf_model() as model:
        r=Eryma(decision_model=model,input_checks=[fixed_check()],output_guard=False).scan_input("Hello")
        assert not r.allowed and r.status=="evaluation_error"
    module.AutoTokenizer.from_pretrained=fail
    with pytest.raises(ModelLoadingError) as exc:hf_model()
    assert "DUMMY" not in str(exc.value)


def test_von_load_and_inference_failures(monkeypatch):
    engines=install_von(monkeypatch)
    with VonAdapter() as model:
        def fail(**kwargs):raise RuntimeError("DUMMY_PRIVATE")
        engines[0].evaluate=fail
        with pytest.raises(InferenceError):model.evaluate(request())
    sys.modules["von.engine"].VonEngine=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("DUMMY_PRIVATE"))
    with pytest.raises(ModelLoadingError):VonAdapter()


@pytest.mark.parametrize("value",[True,-.1,1.1,float("nan"),".7",None])
def test_native_binary_invalid_scores(monkeypatch,value):
    runtime,_=install_laya(monkeypatch)
    with LayaAdapter() as model:
        runtime.payload=answers({c.name:{"type":"noul"} for c in request("output").checks})
        runtime.payload["answers"]["harmful_content"]["noul"]=value
        with pytest.raises(InvalidOutputError):model.evaluate(request("output"))


def test_environment_floor_and_missing_dependency_guidance(monkeypatch):
    import eryma.adapters.von as von_adapter
    monkeypatch.setattr(von_adapter.sys,"version_info",(3,11))
    with pytest.raises(UnsupportedEnvironmentError):VonAdapter()
    real=_shared.importlib.import_module
    def missing(name,*args):
        if name=="httpx":raise ImportError("DUMMY")
        return real(name,*args)
    monkeypatch.setattr(_shared.importlib,"import_module",missing)
    with pytest.raises(MissingDependencyError,match=r"eryma\[jev\]"):
        JevAdapter(model="typesafe/jev-1.13",api_key="DUMMY_ONLY")


def test_device_configuration(monkeypatch):
    monkeypatch.setitem(sys.modules,"torch",fake_torch(cuda=True))
    assert _shared.device_for_torch("auto")=="cuda"
    assert _shared.device_for_torch("cuda:1")=="cuda:1"
    with pytest.raises(UnsupportedEnvironmentError):_shared.device_for_torch("cuda:8")
    monkeypatch.setitem(sys.modules,"torch",fake_torch())
    with pytest.raises(UnsupportedEnvironmentError):_shared.device_for_torch("cuda")


def test_core_and_class_imports_do_not_load_optional_runtimes():
    src=str(Path(__file__).resolve().parents[1]/"src")
    code=f"import sys; sys.path.insert(0,{src!r}); import eryma; from eryma.adapters import JevAdapter,LayaAdapter,VonAdapter,HuggingFaceAdapter; assert not any(n in sys.modules for n in ['torch','transformers','mlx','httpx','laya','von'])"
    subprocess.run([sys.executable,"-I","-c",code],check=True,capture_output=True)


@pytest.mark.parametrize("name",["laya","von"])
def test_direct_example_does_not_shadow_runtime(name):
    root=Path(__file__).resolve().parents[1]
    example=root/"examples"/f"{name}.py"
    code=f"""import sys, runpy
sys.path.insert(0, {str(root/'src')!r})
sys.path.insert(0, {str(root/'examples')!r})
sys.argv=[{str(example)!r}, '--help']
try:
    runpy.run_path({str(example)!r}, run_name='__main__')
except SystemExit as exc:
    assert exc.code == 0
assert {str(root/'examples')!r} not in sys.path
"""
    subprocess.run([sys.executable,"-I","-c",code],check=True,capture_output=True)
