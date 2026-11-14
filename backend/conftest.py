def pytest_configure(config):
    config.addinivalue_line("markers", "slow: multi-second end-to-end tests (all run by default; deselect with -m \"not slow\")")
