from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from pathlib import Path

from jarvis.agent import JarvisAgent

app = FastAPI(title="JARVIS Web Interface")

# Setup static files directory
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize a global agent instance
agent = JarvisAgent()

class ChatRequest(BaseModel):
    message: str

@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text()
    return "<h1>JARVIS Static files not found.</h1>"

@app.post("/api/chat")
async def chat(req: ChatRequest):
    # Run the agent in non-interactive mode
    response = agent.run_non_interactive(req.message)
    return {"response": response}

def main():
    uvicorn.run("jarvis.web:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
