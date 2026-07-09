from askflow.core.trace import generate_trace_id, get_trace_id, trace_id_var


class TestTrace:
    def test_generate_trace_id(self):
        tid = generate_trace_id()
        assert len(tid) == 16
        assert isinstance(tid, str)

    def test_trace_id_context(self):
        token = trace_id_var.set("test-trace-123")
        assert get_trace_id() == "test-trace-123"
        trace_id_var.reset(token)

    def test_default_trace_id(self):
        assert get_trace_id() == "" or isinstance(get_trace_id(), str)
