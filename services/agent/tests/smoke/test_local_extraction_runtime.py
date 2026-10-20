"""Local CLI runtime is selected in fresh processes, never patched into test/Server imports."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "services/agent/scripts"
COPY = ROOT / "agent_test/extraction_agent"


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=90,
    )


@pytest.mark.parametrize("script", ["run_stage2_groups.py", "run_page_workflow_extraction.py"])
@pytest.mark.skipif(not COPY.is_dir(), reason="User-owned ignored agent_test copy is not installed")
def test_both_cli_entrypoints_select_copy_before_loading_extraction(script: str) -> None:
    result = _run(f"""
import runpy,sys
from pathlib import Path
sys.argv=[{script!r},'--help']
try:
    runpy.run_path(str(Path('services/agent/scripts')/{script!r}),run_name='__main__')
except SystemExit as exc:
    assert exc.code==0
root=(Path.cwd()/'agent_test/extraction_agent').resolve()
modules={{name:Path(module.__file__).resolve() for name,module in sys.modules.items()
         if name.startswith('src.agent.extraction_agent') and getattr(module,'__file__',None)}}
assert modules and all(path.is_relative_to(root) for path in modules.values()), modules
print('TEST_RUNTIME_ONLY')
""")
    assert result.returncode == 0, result.stderr
    assert "TEST_RUNTIME_ONLY" in result.stdout


def test_runtime_missing_or_already_formal_loaded_fails_without_fallback(tmp_path: Path) -> None:
    result = _run(f"""
import sys
from pathlib import Path
sys.path.insert(0,{str(SCRIPTS)!r})
from local_extraction_runtime import activate_test_extraction
try:
    activate_test_extraction(Path({str(tmp_path)!r}))
except FileNotFoundError:
    pass
else:
    raise AssertionError('Missing copy must not select production')
copy=Path({str(tmp_path)!r})/'agent_test/extraction_agent'
copy.mkdir(parents=True)
(copy/'__init__.py').write_text('')
(copy/'profiles').mkdir()
sys.path.insert(0,str(Path.cwd()/'services/agent'))
import src.agent.extraction_agent
try:
    activate_test_extraction(Path({str(tmp_path)!r}))
except RuntimeError:
    print('NO_MIXED_RUNTIME')
else:
    raise AssertionError('Already-loaded production modules must be rejected')
""")
    assert result.returncode == 0, result.stderr
    assert "NO_MIXED_RUNTIME" in result.stdout


@pytest.mark.skipif(not COPY.is_dir(), reason="User-owned ignored agent_test copy is not installed")
def test_native_copy_uses_whole_target_pages_and_confirmed_cases_without_network() -> None:
    result = _run(f"""
import asyncio,base64,json,sys
from pathlib import Path
sys.path.insert(0,{str(SCRIPTS)!r})
from local_extraction_runtime import activate_test_extraction
root=activate_test_extraction()
import run_stage2_groups as runner
import httpx,pymupdf
def forbidden(*a,**k):
    raise AssertionError('Network/database forbidden in offline test')
httpx.AsyncClient.request=forbidden
httpx.Client.request=forbidden
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.agent.extraction_agent.domain.models.extraction_stages import (
    PageScanRequest,DrawingPageInput,CrossPageCompletionRequest,CrossPageCompletionData)
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from src.agent.extraction_agent.profiles.extraction_policy import default_extraction_policies
settings=runner.memory_settings(AgentSettings(default_model='fake',persistence_backend='supabase',
    supabase_url='https://database.invalid',supabase_service_role_key='fake'))
assert settings.profile_root==root/'profiles'
assert settings.persistence_backend=='memory' and settings.checkpoint_backend=='memory'
assert not settings.profile_packages_enabled and settings.supabase_url is None
assert settings.supabase_service_role_key is None
profile=runner.load_local_profile(settings,'zh')
assert profile.profile.version=='2.3.1'
assert all(p.is_relative_to(root) for p in profile.resolved_resources.values())
import inspect
policy=default_extraction_policies().resolve(profile.adapter)
assert Path(inspect.getfile(type(policy))).is_relative_to(root)
assets=profile.resource('wiring_examples')
manifest=json.loads((assets/'manifest.json').read_text(encoding='utf-8'))
assert len(manifest['stage2_cases'])==2 and len(manifest['stage3_cases'])==7
assert not json.loads(profile.resource('completion_view_rules').read_text(encoding='utf-8'))['enabled']
def assert_full_image(part,source):
    data=base64.b64decode(part['image_url']['url'].split(',',1)[1])
    actual=pymupdf.Pixmap(data)
    original=pymupdf.Pixmap(str(source))
    assert abs(actual.width/actual.height-original.width/original.height)<.01
async def check():
    for case in manifest['stage2_cases']:
        payload=json.loads((assets/case['expected']).read_text(encoding='utf-8'))
        gateway=FakeModelGateway([json.dumps(payload,ensure_ascii=False)])
        actual=await ZhVlmExtractionStageAdapter(settings,gateway).scan_page(PageScanRequest(
            run_id='offline-copy',project_id='offline',profile=profile,
            page=DrawingPageInput(pdf_page_number=payload['pdf_page_number'],
                                 image_path=assets/case['images'][0]['path'])))
        expected=[(c['line_number'],(c.get('start') or {{}}).get('terminal'),
                   (c.get('end') or {{}}).get('terminal'))
                  for u in payload['units'] for c in u['connections']]
        assert [(c.line_number,c.start.terminal,c.end.terminal if c.end else None)
                for u in actual.units for c in u.connections]==expected
        assert all(u.wire_number is None for u in actual.units)
        if payload['pdf_page_number']==50:
            assert len(expected)==16
            assert sum(c[0]=='003G0121' for c in expected)==2
        prompt=gateway.calls[0].messages[0]['content']
        assert 'wire_number' in prompt and 'line_number' in prompt
        schema=json.loads(prompt.split('输出 JSON Schema：',1)[1])
        assert schema['$defs']['ScannedWireUnit']['properties']['wire_number']['type']=='null'
        assert 'line_number' in schema['$defs']['ScannedConnection']['required']
    for case in manifest['stage3_cases']:
        task=json.loads((assets/case['input']).read_text(encoding='utf-8'))
        gold=json.loads((assets/case['expected']).read_text(encoding='utf-8'))
        gateway=FakeModelGateway([json.dumps(gold,ensure_ascii=False)])
        adapter=ZhVlmExtractionStageAdapter(settings,gateway)
        actual=await adapter.resolve_cross_page(CrossPageCompletionRequest(
            run_id='offline-copy',project_id='offline',profile=profile,task_id=task['task_id'],
            task_context=json.dumps(task,ensure_ascii=False),
            target_page=DrawingPageInput(pdf_page_number=task['target_page']['pdf_page_number'],
                                        image_path=assets/case['images'][0]['path'])))
        expected=CrossPageCompletionData.model_validate(gold)
        assert actual.end==expected.end,case['id']
        assert actual.source_component==expected.source_component,case['id']
        assert actual.source_note==expected.source_note,case['id']
        assert actual.uncertainties==expected.uncertainties,case['id']
        assert actual.current==expected.current,case['id']
        request=gateway.calls[0]
        assert request.metadata['completion_image_view']=={{'mode':'full_page','reason':'disabled'}}
        content=request.messages[-1]['content']
        assert_full_image(content[-1],assets/case['images'][0]['path'])
        assert 'image_view' not in content[0]['text']
        for message in request.messages:
            if message['role']=='user' and isinstance(message['content'],list):
                for part in message['content']:
                    if part.get('type')=='image_url':
                        im=pymupdf.Pixmap(base64.b64decode(part['image_url']['url'].split(',',1)[1]))
                        assert 1.2<im.width/im.height<1.8
asyncio.run(check())
for name,module in sys.modules.items():
    if name.startswith('src.agent.extraction_agent') and getattr(module,'__file__',None):
        assert Path(module.__file__).resolve().is_relative_to(root),(name,module.__file__)
print('TWO_SCANS_SEVEN_COMPLETIONS_FULL_PAGE_NO_NETWORK')
""")
    assert result.returncode == 0, result.stderr
    assert "TWO_SCANS_SEVEN_COMPLETIONS_FULL_PAGE_NO_NETWORK" in result.stdout
