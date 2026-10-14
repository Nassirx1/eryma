import json
import pytest
import httpx
from eryma import Eryma, presets
from eryma.adapters.http import HTTPDecisionModel, ProviderError
from eryma.adapters.decisions_api import DecisionsAPIFormat


def adapter(**kwargs):
    wire=DecisionsAPIFormat(model='developer-chosen-model')
    return HTTPDecisionModel(endpoint=kwargs.pop('endpoint','https://decision.example/evaluate'),
        request_builder=wire.build_request,response_parser=wire.parse_response,**kwargs)


def handler_ok(request):
    payload=json.loads(request.content)
    return httpx.Response(200,json={'answers':{k:({'type':'noul','noul':.35} if q['type']=='noul' else
        {'type':'choice','choice':'jailbreak','confidence':0,'probabilities':{'safe':.3,'prompt_injection':.28,'jailbreak':.22,'harmful_request':.2}})
        for k,q in payload['questions'].items()}})


def test_wire_format_trust_separation_and_binary_complement():
    calls=[]
    def handler(req):calls.append(req);return handler_ok(req)
    with adapter(api_key='TEST_ONLY',transport=httpx.MockTransport(handler)) as model:
        guard=Eryma(decision_model=model,objective='Bank support only',security_policy='No transactions')
        r=guard.scan_input('INJECT_UNTRUSTED',external_content='EXTERNAL_UNTRUSTED')
        assert r.allowed and r.selected_decision=='safe'
        r=guard.scan_output('OUTPUT_UNTRUSTED',user_prompt='INJECT_UNTRUSTED')
        assert r.allowed and r.checks[0].confidence==.65
    for req in calls:
        assert str(req.url)=='https://decision.example/evaluate'
        assert req.headers['Authorization']=='Bearer TEST_ONLY'
        data=json.loads(req.content)
        assert data['state']['trusted_context']['objective']=='Bank support only'
        assert data['state']['trusted_context']['security_policy']=='No transactions'
        assert 'UNTRUSTED' not in json.dumps(data['questions'])
        assert 'UNTRUSTED' in json.dumps(data['state']['untrusted_data'])


@pytest.mark.parametrize('status',[301,401,429,500])
def test_http_no_redirects_retries_or_error_body(status):
    calls=[]
    def handler(req):calls.append(req);return httpx.Response(status,text='PRIVATE',headers={'location':'https://evil.invalid'})
    with adapter(api_key='TEST_ONLY',transport=httpx.MockTransport(handler)) as model:
        result=Eryma(decision_model=model).scan_input('Hi')
    assert not result.allowed and len(calls)==1 and 'PRIVATE' not in repr(result)


@pytest.mark.parametrize('payload',[{}, {'answers':None},{'answers':{}}, {'error':'PRIVATE'},
    {'answers':{'classification':{'type':'noul','noul':.1}}}])
def test_bad_provider_shape(payload):
    with adapter(api_key='TEST_ONLY',transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload))) as model:
        assert Eryma(decision_model=model).scan_input('Hi').status=='evaluation_error'


@pytest.mark.parametrize('value',[-1,2,True,None,'0.1'])
def test_bad_binary_score(value):
    with adapter(api_key='TEST_ONLY',transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'answers':{'risk':{'type':'noul','noul':value}}}))) as model:
        assert not Eryma(decision_model=model,output_checks=[presets.binary_check('risk','Risk?')]).scan_output('Hi').allowed


def test_transport_failure_and_invalid_json():
    def broken(req):raise httpx.ReadTimeout('PRIVATE',request=req)
    for handler in (broken,lambda r:httpx.Response(200,text='PRIVATE')):
        with adapter(api_key='TEST_ONLY',transport=httpx.MockTransport(handler)) as model:
            result=Eryma(decision_model=model).scan_input('Hi')
            assert not result.allowed and 'PRIVATE' not in repr(result)


@pytest.mark.parametrize('url',['http://example.com','https://user:pass@example.com','https://example.com?key=x','https://example.com#x'])
def test_invalid_urls(url):
    with pytest.raises(ValueError):adapter(api_key='TEST_ONLY',endpoint=url)


@pytest.mark.parametrize('kwargs',[{'api_key':''},{'api_key':'x','timeout':float('nan')},{'api_key':'x','timeout':0}])
def test_adapter_validation(kwargs):
    with pytest.raises(ValueError):adapter(**kwargs)


def test_arbitrary_provider_schema_and_custom_auth():
    from eryma import ScoreDistribution
    calls = []
    def handler(request):
        calls.append(request)
        assert json.loads(request.content) == {'document': 'hello'}
        assert request.headers['X-Decision-Token'] == 'TEST_ONLY'
        assert 'authorization' not in request.headers
        return httpx.Response(200, json={'risk_score': .1})
    def parse(data, request):
        return {check.name: ScoreDistribution({'violation': data['risk_score'],
            'no_violation': 1-data['risk_score']}) for check in request.checks}
    with HTTPDecisionModel(endpoint='https://custom.example/risk',
            headers={'X-Decision-Token': 'TEST_ONLY'},
            request_builder=lambda r: {'document': r.untrusted_data['user_message']},
            response_parser=parse, transport=httpx.MockTransport(handler)) as model:
        result = Eryma(decision_model=model, input_checks=[presets.binary_check('risk', 'Risk?')]).scan_input('hello')
    assert result.allowed and len(calls) == 1


def test_conflicting_auth_rejected():
    with pytest.raises(ValueError):
        adapter(api_key='TEST_ONLY', headers={'Authorization': 'Custom TEST_ONLY'})
