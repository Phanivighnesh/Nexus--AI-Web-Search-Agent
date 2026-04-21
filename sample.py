# Check whether you are eligible to use
from groq import Groq
client = Groq(api_key="Your API Key")
models = client.models.list()
for m in models.data:
    print(m.id)