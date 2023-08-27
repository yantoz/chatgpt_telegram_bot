
from typing import Any,Optional

# Create an empty dictionary to store data
import uuid
from datetime import datetime

import config


class Database:
  def __init__(self):
    self.database = {}
  # Define a function to check if a user exists
  def check_if_user_exists(self, user_id: int, raise_exception: bool = False):
    if user_id in self.database:
      return True
    else:
      if raise_exception:
        raise ValueError(f"User {user_id} does not exist")
      else:
        return False

  # Define a function to add a new user
  def add_new_user(
    self,
    user_id: int,
    chat_id: int,
    username: str = "",
    first_name: str = "",
    last_name: str = "",
  ):
    user_dict = {
      "chat_id": chat_id,
      "username": username,
      "first_name": first_name,
      "last_name": last_name,
      "last_interaction": datetime.now(),
      "first_seen": datetime.now(),
      "current_dialog_id": None,
      "current_chat_mode": "assistant",
      "current_model": config.models["available_text_models"][0],
      "current_image_model": "stablediffusion",
      "n_used_tokens": {},
      "n_generated_images": 0,
      "n_transcribed_seconds": 0.0 # voice message transcription
    }

    if not self.check_if_user_exists(user_id):
      self.database[user_id] = user_dict

  # Define a function to start a new dialog
  def start_new_dialog(self, user_id: int):
    self.check_if_user_exists(user_id, raise_exception=True)

    dialog_id = str(uuid.uuid4())
    dialog_dict = {
      "_id": dialog_id,
      "user_id": user_id,
      "chat_mode": self.get_user_attribute(user_id, "current_chat_mode"),
      "start_time": datetime.now(),
      "model": self.get_user_attribute(user_id, "current_model"),
      "messages": []
    }

    # add new dialog
    self.database[user_id]["current_dialog"] = dialog_dict

    # update user's current dialog id
    self.database[user_id]["current_dialog_id"] = dialog_id

    return dialog_id

  # Define a function to get a user attribute
  def get_user_attribute(self, user_id: int, key: str):
    self.check_if_user_exists(user_id, raise_exception=True)
    user_dict = self.database[user_id]

    if key not in user_dict:
      return None

    return user_dict[key]

  # Define a function to set a user attribute
  def set_user_attribute(self, user_id: int, key: str, value: Any):
    self.check_if_user_exists(user_id, raise_exception=True)
    self.database[user_id][key] = value

  # Define a function to update n used tokens
  def update_n_used_tokens(self, user_id: int, model: str, n_input_tokens: int, n_output_tokens: int):
    n_used_tokens_dict = self.get_user_attribute(user_id, "n_used_tokens")

    if model in n_used_tokens_dict:
      n_used_tokens_dict[model]["n_input_tokens"] += n_input_tokens
      n_used_tokens_dict[model]["n_output_tokens"] += n_output_tokens
    else:
      n_used_tokens_dict[model] = {
        "n_input_tokens": n_input_tokens,
        "n_output_tokens": n_output_tokens
      }

    self.set_user_attribute(user_id, "n_used_tokens", n_used_tokens_dict)

  # Define a function to get dialog messages
  def get_dialog_messages(self, user_id: int, dialog_id: Optional[str] = None):
    self.check_if_user_exists(user_id, raise_exception=True)

    if dialog_id is None:
      dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

    dialog_dict = self.database[user_id]["current_dialog"]
    
    # check if the dialog id matches
    if dialog_dict["_id"] != dialog_id:
      raise ValueError(f"Dialog {dialog_id} does not exist for user {user_id}")

    return dialog_dict["messages"]

  # Define a function to set dialog messages
  def set_dialog_messages(self, user_id: int, dialog_messages: list, dialog_id: Optional[str] = None):
    self.check_if_user_exists(user_id, raise_exception=True)

    if dialog_id is None:
      dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

    dialog_dict = self.database[user_id]["current_dialog"]

    # check if the dialog id matches
    if dialog_dict["_id"] != dialog_id:
      raise ValueError(f"Dialog {dialog_id} does not exist for user {user_id}")

    dialog_dict["messages"] = dialog_messages
