import openai
#from langchain.embeddings import HuggingFaceEmbeddings
from langchain_community.embeddings import LocalAIEmbeddings
import uuid
import sys
from queue import Queue
import asyncio
import threading
from localagi import LocalAGI
from loguru import logger
from ascii_magic import AsciiArt
from duckduckgo_search import DDGS
from typing import Dict, List
import os
import requests

from telegram.constants import ParseMode, ChatAction

from langchain_community.document_loaders import (
    SitemapLoader,
   # GitHubIssuesLoader,
   # GitLoader,
)

# these three lines swap the stdlib sqlite3 lib with the pysqlite3 package for chroma
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
from langchain.text_splitter import RecursiveCharacterTextSplitter
import urllib.request
from datetime import datetime

from langchain_community.vectorstores import Chroma
from chromadb.config import Settings
import json
import os
from io import StringIO 
FILE_NAME_FORMAT = '%Y_%m_%d_%H_%M_%S'

EMBEDDINGS_MODEL = os.environ.get("EMBEDDINGS_MODEL", "all-MiniLM-L6-v2")
EMBEDDINGS_API_BASE = os.environ.get("EMBEDDINGS_API_BASE", "http://api:8080")
PERSISTENT_DIR = os.environ.get("PERSISTENT_DIR", "/data")
DB_DIR = os.environ.get("DB_DIR",  "/data/db" )
embeddings = LocalAIEmbeddings(model=EMBEDDINGS_MODEL,openai_api_base=EMBEDDINGS_API_BASE)

updateHandle = None

# Create a queue to hold the asynchronous tasks
task_queue = Queue()

# A worker function that runs the asyncio event loop and processes tasks from the queue
def worker():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        task = task_queue.get()
        loop.run_until_complete(task)
        task_queue.task_done()

# Start the worker thread
worker_thread = threading.Thread(target=worker)
worker_thread.start()

### Agent capabilities
### These functions are called by the agent to perform actions
###

def ingest(a, agent_actions={}, localagi=None):
    q = json.loads(a)
    chunk_size = 500
    chunk_overlap = 50
    logger.info(">>> ingesting: ")
    logger.info(q)
    documents = []
    sitemap_loader = SitemapLoader(web_path=q["url"])
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    documents.extend(sitemap_loader.load())
    texts = text_splitter.split_documents(documents)
    db = Chroma.from_documents(texts,embeddings,collection_name="memories", persist_directory=DB_DIR)
    db.persist()
    db = None
    return f"Documents ingested"

def create_image(a, agent_actions={}, localagi=None):
    q = json.loads(a)
    logger.info(">>> creating image: ") 
    logger.info(q["caption"])
    size=f"{q['width']}x{q['height']}"
    response = openai.Image.create(prompt=q["caption"], n=1, size=size)
    image_url = response["data"][0]["url"]
    file_path=""
    if updateHandle is not None:
        task_queue.put(updateHandle.message.chat.send_action(action="upload_photo"))
        # Download the image from the URL
        response = requests.get(image_url)
        if response.status_code == 200:
            # Save the image to a file
            file_path = f"image_{datetime.now().strftime(FILE_NAME_FORMAT)}.jpg"  # Choose a file name and extension
            with open(file_path, "wb") as file:
                file.write(response.content)
            
            task_queue.put(updateHandle.message.reply_photo(file_path, parse_mode=ParseMode.HTML))
        else:
            task_queue.put(updateHandle.message.reply_text("Failed to download the image."))
        task_queue.join()  # Wait for all tasks to complete
        # Remove the saved image file
        if os.path.exists(file_path):
            os.remove(file_path)
    return f"Image created: {image_url}"

def download_image(url: str):
    file_name = f"{datetime.now().strftime(FILE_NAME_FORMAT)}.jpg"
    full_path = f"{PERSISTENT_DIR}{file_name}"
    urllib.request.urlretrieve(url, full_path)
    return file_name

def save(memory, agent_actions={}, localagi=None):
    q = json.loads(memory)
    logger.info(">>> saving to memories: ") 
    logger.info(q["content"])
    chroma_client = Chroma(collection_name="memories", persist_directory=DB_DIR, embedding_function=embeddings)
    chroma_client.add_texts([q["content"]],[{"id": str(uuid.uuid4())}])
    chroma_client.persist()
    return f"The object was saved permanently to memory."

def search_memory(query, agent_actions={}, localagi=None):
    q = json.loads(query)
    chroma_client = Chroma(collection_name="memories", persist_directory=DB_DIR, embedding_function=embeddings)
    docs = chroma_client.similarity_search(q["reasoning"])
    text_res="Memories found in the database:\n"
    for doc in docs:
        text_res+="- "+doc.page_content+"\n"

    #if args.postprocess:
    #    return post_process(text_res)
    #return text_res
    return localagi.post_process(text_res)

# write file to disk with content
def save_file(arg, agent_actions={}, localagi=None):
    arg = json.loads(arg)
    filename = arg["filename"]
    content = arg["content"]
    # create persistent dir if does not exist
    if not os.path.exists(PERSISTENT_DIR):
        os.makedirs(PERSISTENT_DIR)
    # write the file in the directory specified
    filename = os.path.join(PERSISTENT_DIR, filename)

    # Check if the file already exists
    if os.path.exists(filename):
        mode = 'a'  # Append mode
    else:
        mode = 'w'  # Write mode

    with open(filename, mode) as f:
        f.write(content)

    if updateHandle is not None:
       task_queue.put(updateHandle.message.reply_document(
            document=open(filename, "rb"),
            filename=filename,
            caption="result"
        ))
    task_queue.join()  # Wait for all tasks to complete
    return f"File {filename} saved successfully."

def ddg(query: str, num_results: int, backend: str = "api") -> List[Dict[str, str]]:
    """Run query through DuckDuckGo and return metadata.

    Args:
        query: The query to search for.
        num_results: The number of results to return.

    Returns:
        A list of dictionaries with the following keys:
            snippet - The description of the result.
            title - The title of the result.
            link - The link to the result.
    """
    ddgs = DDGS()
    try:
        results = ddgs.text(
            query,
            backend=backend,
        )
        if results is None:
            return [{"Result": "No good DuckDuckGo Search Result was found"}]

        def to_metadata(result: Dict) -> Dict[str, str]:
            if backend == "news":
                return {
                    "date": result["date"],
                    "title": result["title"],
                    "snippet": result["body"],
                    "source": result["source"],
                    "link": result["url"],
                }
            return {
                "snippet": result["body"],
                "title": result["title"],
                "link": result["href"],
            }

        formatted_results = []
        for i, res in enumerate(results, 1):
            if res is not None:
                formatted_results.append(to_metadata(res))
            if len(formatted_results) == num_results:
                break
    except Exception as e:
        logger.error(e)
        return []
    return formatted_results

## Search on duckduckgo
def search_duckduckgo(a, agent_actions={}, localagi=None):
    a = json.loads(a)
    list=ddg(a["query"], 2)

    text_res=""   
    for doc in list:
        text_res+=f"""{doc["link"]}: {doc["title"]} {doc["snippet"]}\n"""  

    #if args.postprocess:
    #    return post_process(text_res)
    return text_res
    #l = json.dumps(list)
    #return l

### End Agent capabilities
###

### Agent action definitions
agent_actions = {
  "ingest": {
        "function": ingest,
        "plannable": True,
        "description": 'The assistant replies with the action "ingest" when there is an url to a sitemap to ingest memories from.',
        "signature": {
            "name": "ingest",
            "description": """Save or store informations into memory.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "information to save"
                    },
                },
                "required": ["url"]
            }
        },
    },
  "generate_picture": {
        "function": create_image,
        "plannable": True,
        "description": 'For creating a picture, the assistant replies with "generate_picture" and a detailed caption, enhancing it with as much detail as possible.',
        "signature": {
            "name": "generate_picture",
            "parameters": {
                "type": "object",
                "properties": {
                    "caption": {
                        "type": "string",
                    },
                    "width": {
                        "type": "number",
                    },
                    "height": {
                        "type": "number",
                    },
                },
            }
        },
    },
    "search_internet": {
        "function": search_duckduckgo,
        "plannable": True,
        "description": 'For searching the internet with a query, the assistant replies with the action "search_internet" and the query to search.',
        "signature": {
            "name": "search_internet",
            "description": """For searching internet.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "information to save"
                    },
                },
            }
        },
    },
    "save_file": {
        "function": save_file,
        "plannable": True,
        "description": 'The assistant replies with the action "save_file", the filename and content to save for writing a file to disk permanently. This can be used to store the result of complex actions locally.',
        "signature": {
            "name": "save_file",
            "description": """For saving a file to disk with content.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "information to save"
                    },
                    "content": {
                        "type": "string",
                        "description": "information to save"
                    },
                },
            }
        },
    },
    "save_memory": {
        "function": save,
        "plannable": True,
        "description": 'The assistant replies with the action "save_memory" and the string to remember or store an information that thinks it is relevant permanently.',
        "signature": {
            "name": "save_memory",
            "description": """Save or store informations into memory.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "information to save"
                    },
                },
                "required": ["content"]
            }
        },
    },
    "search_memory": {
        "function": search_memory,
        "plannable": True,
        "description": 'The assistant replies with the action "search_memory" for searching between its memories with a query term.',
        "signature": {
            "name": "search_memory",
            "description": """Search in memory""",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "reasoning behind the intent"
                    },
                },
                "required": ["reasoning"]
            }
        }, 
    },
}
