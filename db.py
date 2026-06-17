import os
from cs50 import SQL
from groq import Groq

db = SQL("sqlite:///upward.db")

groq_client = Groq(
    api_key=os.environ.get("GROQ_API_KEY")
)