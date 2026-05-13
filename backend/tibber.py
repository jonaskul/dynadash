from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import config
from tibber_db import delete_setting, get_setting, set_setting
from tibber_pulse import pulse_manager, rest_poller

logger = logging.getLogger(__name__)