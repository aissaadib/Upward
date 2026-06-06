import ollama 
client = ollama.Client()

model = "gemma3"
prompt = "hello?"

response = client.generate(model=model,prompt=prompt)

print(response.response)