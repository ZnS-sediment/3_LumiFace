import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('stop_scope',Path(__file__).resolve().parents[2]/'scripts/stop_local_servers.py')
stop=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stop)


def test_only_exact_checkout_web_servers_are_selected():
    root=Path('/project/3_LumiFace')
    assert stop.is_project_server(['python','-m','uvicorn','app.main:app'],root,root)
    assert stop.is_project_server(['node',str(root/'frontend/node_modules/.bin/vite')],root/'frontend',root)
    assert not stop.is_project_server(['python','experiments/scripts/benchmark_public.py','cbsr-nir'],root,root)
    assert not stop.is_project_server(['python','-m','uvicorn','app.main:app'],Path('/other-project'),root)
    assert not stop.is_project_server(['node','vite'],root,root)
