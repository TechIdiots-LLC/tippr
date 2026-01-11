"""Sorting helpers and time utilities.

This module prefers a compiled `_sorts` Cython extension when available
but provides a pure-Python fallback so tests and imports work when the
extension is not built.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

try:
	from pylons import app_globals as g
except Exception:  # pragma: no cover - pylons globals missing in some test setups
	g = None

try:
	# Prefer the compiled Cython extension when present.
	from ._sorts import (
		epoch_seconds,
		score,
		hot,
		_hot,
		controversy,
		confidence,
		qa,
		_qa,
	)
except Exception:
	# Pure-Python fallbacks matching the logic from the original Cython
	# implementation. These are slightly slower but fully functional for
	# tests and environments without compiled extensions.

	if g is None:
		# Create a minimal timezone-aware stub if pylons.app_globals isn't
		# available; naive datetimes will be used in that case.
		class _G:
			tz = None


		g = _G()

	epoch = datetime(1970, 1, 1, tzinfo=getattr(g, "tz", None))


	def epoch_seconds(date: datetime) -> float:
		"""Return seconds since epoch (float)."""
		td = date - epoch
		return td.days * 86400 + td.seconds + (float(td.microseconds) / 1000000)


	def score(ups: int, downs: int) -> int:
		return ups - downs


	def _hot(ups: int, downs: int, date_seconds: float) -> float:
		"""The hot formula.

		Matches the original function used by the codebase.
		"""
		s = score(ups, downs)
		order = math.log10(max(abs(s), 1))
		if s > 0:
			sign = 1
		elif s < 0:
			sign = -1
		else:
			sign = 0
		seconds = date_seconds - 1134028003
		return round(sign * order + seconds / 45000, 7)


	def hot(ups: int, downs: int, date: datetime) -> float:
		return _hot(ups, downs, epoch_seconds(date))


	def controversy(ups: int, downs: int) -> float:
		if downs <= 0 or ups <= 0:
			return 0

		magnitude = ups + downs
		balance = float(downs) / ups if ups > downs else float(ups) / downs

		return magnitude ** balance


	def _confidence(ups: int, downs: int) -> float:
		n = ups + downs
		if n == 0:
			return 0.0
		z = 1.281551565545  # 80% confidence
		p = float(ups) / n
		left = p + 1 / (2 * n) * z * z
		right = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
		under = 1 + 1 / n * z * z
		return (left - right) / under


	up_range = 400
	down_range = 100
	_confidences = []
	for ups in range(up_range):
		for downs in range(down_range):
			_confidences.append(_confidence(ups, downs))


	def confidence(ups: int, downs: int) -> float:
		if ups + downs == 0:
			return 0
		elif ups < up_range and downs < down_range:
			return _confidences[downs + ups * down_range]
		else:
			return _confidence(ups, downs)


	def _qa(question_score: float, question_length: int, answer_score: float = 0, answer_length: int = 1) -> float:
		score_modifier = question_score + answer_score
		length_modifier = math.log10(question_length + answer_length)
		return score_modifier + (length_modifier / 5)


	def qa(question_ups: int, question_downs: int, question_length: int, op_children) -> float:
		question_score = confidence(question_ups, question_downs)
		if not op_children:
			return _qa(question_score, question_length)
		best_score = None
		answer_length = 1
		for answer in op_children:
			sc = confidence(answer._ups, answer._downs)
			if best_score is None or sc > best_score:
				best_score = sc
				answer_length = len(getattr(answer, "body", ""))
		return _qa(question_score, question_length, best_score or 0, answer_length)


