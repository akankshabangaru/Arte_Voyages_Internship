import pathlib
def test_dashboard_imports_without_network():
    assert pathlib.Path("dashboard.py").exists()
    assert "streamlit" in pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    assert "get_alerts" in pathlib.Path("dashboard.py").read_text(encoding="utf-8")
