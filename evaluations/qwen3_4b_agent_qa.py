"""Explicit opt-in QA provider; importing this module never starts inference.

Use only with a separately managed Ollama instance on the QA port. The server
must independently enforce OLLAMA_NUM_PARALLEL=1 and pass resource admission.
"""
from src.agent.providers import HybridLLM, JSONProvider


class Qwen4BQAProvider(JSONProvider):
    def __init__(self):
        super().__init__('offline', model='qwen3:4b-q4_K_M',
                         url='http://127.0.0.1:11479/api/chat')
        self.num_ctx = 4096

    def payload(self, messages, schema=None):
        context = ('You are the BioReactor AI assistant for anaerobic digestion and biogas. '
                   'In this domain an unqualified BMP means biochemical methane potential; '
                   'respect an explicit question about the bitmap image format.')
        result = super().payload([{'role':'system','content':context}, *messages], schema)
        result['options'].update(num_ctx=4096, num_batch=32, num_gpu=-1)
        result['keep_alive'] = 0
        return result


def create_qa_llm():
    return HybridLLM('offline', providers=[Qwen4BQAProvider()], strict_model=True)
