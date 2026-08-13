#!/usr/bin/env python3
"""마커 사이를 다시 쓴다. 생성물을 사람이 쓴 문서 안에 심는 유일한 방법.

`commands.py`(명령 블록)와 `stacks.py`(카탈로그 블록)가 같은 일을 해야 해서 여기로 뺐다.
직접 겹쳐 쓰지 않고 마커를 쓰는 이유는 **마커 밖의 사람 손 편집이 살아남아야** 하기 때문이다 —
생성물이 문서를 통째로 소유하면 아무도 그 문서에 설명을 못 쓴다.
"""
from __future__ import annotations

from pathlib import Path


def splice(text: str, start: str, end: str, body: str) -> str:
    """`start` 다음부터 `end` 앞까지를 `body` 로 갈아 끼운다.

    마커가 없으면 조용히 넘어가지 않고 실패한다 — 마커를 지운 문서에 생성물이 사라진 채
    "최신" 으로 통과하는 것이 이 장치의 false negative 다.
    """
    lines = text.splitlines()
    try:
        i = lines.index(start)
        j = lines.index(end)
    except ValueError:
        raise LookupError(f"마커를 찾지 못했다:\n  {start}\n  {end}")
    if j < i:
        raise LookupError(f"마커 순서가 뒤집혔다:\n  {start}\n  {end}")
    return "\n".join(lines[: i + 1] + body.splitlines() + lines[j:]) + "\n"


def apply_block(path: Path, markers: tuple[str, str], body: str, write: bool) -> bool:
    """파일의 블록을 갱신한다. 바뀐(또는 바뀌어야 할) 경우 True.

    쓰기 뒤에 되읽어 대조한다 (P09 — 쓰기 경로마다 되읽기 검사를 짝짓는다).
    """
    old = path.read_text(encoding="utf-8")
    new = splice(old, markers[0], markers[1], body)
    if new == old:
        return False
    if write:
        path.write_text(new, encoding="utf-8")
        if path.read_text(encoding="utf-8") != new:
            raise OSError(f"{path} 를 썼지만 되읽은 내용이 다르다.")
    return True
