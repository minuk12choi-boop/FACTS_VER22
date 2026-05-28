"""FACTS views facade.

urls.py의 기존 from . import views 패턴 호환을 위해 함수명을 재노출한다.
"""

from .view_modules.dashboard import *
from .view_modules.history import *
from .view_modules.prevent_tip import *
from .view_modules.master import *
from .view_modules.kpi import *
from .view_modules.voc import *

