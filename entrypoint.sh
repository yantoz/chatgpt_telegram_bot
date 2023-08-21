#!/bin/bash

pip uninstall hnswlib chromadb-hnswlib -y
pip install hnswlib chromadb-hnswlib
cd /code
python3 /code/bot/bot.py