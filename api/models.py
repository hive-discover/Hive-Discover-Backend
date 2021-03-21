from pydantic import BaseModel, Field
from typing import Dict, Optional, List
from enum import Enum

import sys, os
sys.path.append(os.getcwd() + "/.")
from config import *

class LabelValueItem(BaseModel):
    label : str
    value : float

class Failed(BaseModel):
    status : Optional[str]
    info : Optional[str]
    msg : Optional[Dict]
    code : Optional[int]

class Succes(BaseModel):
    status : Optional[str]
    info : Optional[str]
    msg : Optional[Dict]
    code : Optional[int]


#   *** Posts ***
class PostItem(BaseModel):
    author : str
    permlink : str
    lang : Optional[List[str]] = []
    tags : Optional[List[str]] = []

class PostsSearch(BaseModel):
    query : str = Field(None, max_length=250, min_length=1)
    lang : Optional[List[str]] = []
    max : Optional[int] = Field(100, gt=0, ls=500)

class PostsResponse(BaseModel):
    posts : List[PostItem]
    status : str = "failed"
    amount : int = 0
    total : Optional[int]
    seconds : Optional[float]


#   *** Accounts ***

class AccountsSearch(BaseModel):
    query : str = Field(min_length=1, max_length=500)
    max : Optional[int] = Field(50, gt=0, ls=500)

class AccountSearchResponse(BaseModel):
    accounts : List[str]
    status : str = "failed"
    amount : int = 0
    total : Optional[int]
    seconds : Optional[float]

class AccountData(BaseModel):
    username : str
    status : str = "failed"
    info : Optional[str] 
    categories : Optional[List[LabelValueItem]]
    language : Optional[List[LabelValueItem]]
    loading : Optional[Dict]


#   *** Tokens ***
class AccountToken(BaseModel):
    access_token : str



