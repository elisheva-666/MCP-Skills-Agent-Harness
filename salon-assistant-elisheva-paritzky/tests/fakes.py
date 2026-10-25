"""A scripted stand-in for anthropic.Anthropic, so harness tests need no key and no network."""
from types import SimpleNamespace


class Block(SimpleNamespace):
    def to_dict(self):
        return dict(vars(self))


def text(t):
    return Block(type="text", text=t)


def tool_use(id, name, input):
    return Block(type="tool_use", id=id, name=name, input=input)


def response(*blocks, stop="end_turn", input=100, cache_read=0, cache_write=0, output=20):
    usage = SimpleNamespace(input_tokens=input, cache_read_input_tokens=cache_read,
                            cache_creation_input_tokens=cache_write, output_tokens=output)
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=usage)


class FakeClient:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.requests = []
        api = SimpleNamespace(create=self._create)
        self.messages = api
        self.beta = SimpleNamespace(messages=api)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.queue.pop(0)
