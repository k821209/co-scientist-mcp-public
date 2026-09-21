"""Build a tracked-changes .docx directly — real w:ins / w:del, no LibreOffice.

The skill's mandated path (an isolated profile, a Basic macro calling
.uno:CompareDocuments) failed silently on a Linux host and is flaky on macOS:
soffice idle at 0% CPU, no output, exit 0, nothing in the log (feedback
f34c7df38102). What worked was ~120 lines of lxml + difflib, and it has a
property the LibreOffice path cannot have: it can VERIFY ITSELF. Accepting
every mark must reproduce NEW exactly, rejecting every mark must reproduce
OLD exactly, and both are checked in-process before the file is written.
That is what catches a deleted paragraph landing one slot early — invisible
to every other check in the skill's step 6.

Scope, stated plainly: body paragraphs (top-level `w:p`) are aligned in order
and diffed word by word; a paragraph whose runs carry anything but text
(a drawing, a field, a footnote reference) is replaced whole rather than
rebuilt; tables come from NEW unmarked, which is what the skill's step 5 does
to LibreOffice's output anyway. Formatting-only revisions and moved text are
not produced — the LibreOffice compare remains the fallback for those.
"""
from __future__ import annotations

import copy
import difflib
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{" + W_NS + "}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_TOKEN = re.compile(r"\s+|[^\s]+")
# Run children that carry something other than plain text; a paragraph with
# any of these is not rebuilt run by run.
_NON_TEXT = {W + "drawing", W + "pict", W + "footnoteReference", W + "endnoteReference",
             W + "fldChar", W + "instrText", W + "object", W + "sym", W + "commentReference"}


def _lxml():
    try:
        import lxml.etree as ET  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("lxml is required: pip install lxml") from e
    return ET


def _read_document_xml(path: Path) -> bytes:
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml")


def _body(root):
    body = root.find(W + "body")
    if body is None:
        raise ValueError("document.xml has no w:body")
    return body


def para_text(p) -> str:
    """The text a reader sees in a paragraph: w:t, tabs and breaks."""
    out = []
    for el in p.iter():
        if el.tag == W + "t" or el.tag == W + "delText":
            out.append(el.text or "")
        elif el.tag == W + "tab":
            out.append("\t")
        elif el.tag == W + "br":
            out.append("\n")
    return "".join(out)


def body_texts(root) -> list[str]:
    return [para_text(p) for p in _body(root) if p.tag == W + "p"]


def _has_non_text(p) -> bool:
    return any(el.tag in _NON_TEXT for el in p.iter())


class _Marks:
    def __init__(self, ET, author: str, date: str):
        self.ET, self.author, self.date = ET, author, date
        self.next_id = 1
        self.ins = self.dels = 0

    def _wrap(self, kind: str):
        el = self.ET.Element(W + kind)
        el.set(W + "id", str(self.next_id)); self.next_id += 1
        el.set(W + "author", self.author)
        el.set(W + "date", self.date)
        return el

    def run(self, text: str, rpr, *, deleted: bool = False):
        r = self.ET.Element(W + "r")
        if rpr is not None:
            r.append(copy.deepcopy(rpr))
        t = self.ET.SubElement(r, W + ("delText" if deleted else "t"))
        t.text = text
        t.set(XML_SPACE, "preserve")
        return r

    def ins_run(self, text: str, rpr):
        w = self._wrap("ins"); w.append(self.run(text, rpr)); self.ins += 1
        return w

    def del_run(self, text: str, rpr):
        w = self._wrap("del"); w.append(self.run(text, rpr, deleted=True)); self.dels += 1
        return w

    def mark_paragraph(self, p, kind: str):
        """Mark the paragraph MARK as inserted/deleted (w:pPr/w:rPr/w:ins|del),
        so an accepted deletion merges the paragraph away."""
        ppr = p.find(W + "pPr")
        if ppr is None:
            ppr = self.ET.Element(W + "pPr"); p.insert(0, ppr)
        rpr = ppr.find(W + "rPr")
        if rpr is None:
            rpr = self.ET.SubElement(ppr, W + "rPr")
        rpr.append(self._wrap(kind))


def _first_rpr(p):
    for r in p.iter(W + "r"):
        rpr = r.find(W + "rPr")
        if rpr is not None:
            return rpr
    return None


_PAIR_MIN = 0.45   # quick_ratio below this: not the same paragraph revised, but a swap


def _pair_by_similarity(old_texts, new_texts, i1, i2, j1, j2) -> list[tuple[int, int]]:
    """Best matches first across the whole block (real ratio, not the
    character-multiset upper bound, which pairs any two English sentences),
    each old and new paragraph used once, then the longest increasing run of
    (old index, new index) so pairings cannot cross."""
    scored = []
    for i in range(i1, i2):
        for j in range(j1, j2):
            r = difflib.SequenceMatcher(None, old_texts[i], new_texts[j], autojunk=False).ratio()
            if r >= _PAIR_MIN:
                scored.append((r, i, j))
    scored.sort(reverse=True)
    pair_of: dict[int, int] = {}
    used_new: set[int] = set()
    for _, i, j in scored:
        if i in pair_of or j in used_new:
            continue
        pair_of[i] = j
        used_new.add(j)
    seq = sorted(pair_of.items())
    runs: list[list[tuple[int, int]]] = []
    for k in range(len(seq)):
        cand = max((run for run in runs if run[-1][1] < seq[k][1]), key=len, default=[])
        runs.append(cand + [seq[k]])
    return max(runs, key=len, default=[])


def _rebuild_word_diff(ET, marks: _Marks, new_p, old_text: str, new_text: str):
    """Replace new_p's runs with plain/ins/del runs from a word-level diff.
    Keeps w:pPr; formatting of the first run is applied to every run."""
    rpr = _first_rpr(new_p)
    for child in list(new_p):
        if child.tag not in (W + "pPr", W + "bookmarkStart", W + "bookmarkEnd"):
            new_p.remove(child)
    a, b = _TOKEN.findall(old_text), _TOKEN.findall(new_text)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            new_p.append(marks.run("".join(b[j1:j2]), rpr))
        else:
            if i2 > i1:
                new_p.append(marks.del_run("".join(a[i1:i2]), rpr))
            if j2 > j1:
                new_p.append(marks.ins_run("".join(b[j1:j2]), rpr))


def _as_deleted_copy(ET, marks: _Marks, old_p):
    """A deleted paragraph: every run wrapped in w:del with delText, mark deleted."""
    p = copy.deepcopy(old_p)
    for r in list(p.iter(W + "r")):
        parent = r.getparent()
        if parent is None or parent.tag in (W + "del", W + "ins"):
            continue
        for t in r.iter(W + "t"):
            t.tag = W + "delText"
        w = marks._wrap("del"); marks.dels += 1
        parent.replace(r, w); w.append(r)
    marks.mark_paragraph(p, "del")
    return p


def _mark_inserted(ET, marks: _Marks, new_p):
    for r in list(new_p.iter(W + "r")):
        parent = r.getparent()
        if parent is None or parent.tag in (W + "del", W + "ins"):
            continue
        w = marks._wrap("ins"); marks.ins += 1
        parent.replace(r, w); w.append(r)
    marks.mark_paragraph(new_p, "ins")


def accept_all(root) -> None:
    """Resolve every mark as accepted: deletions vanish, insertions stay."""
    body = _body(root)
    for d in list(root.iter(W + "del")):
        par = d.getparent()
        if par is not None:
            par.remove(d)
    for ins in list(root.iter(W + "ins")):
        par = ins.getparent()
        if par is None:
            continue
        if par.tag == W + "rPr":
            par.remove(ins)          # paragraph-mark insertion: mark stays, nothing to do
            continue
        i = list(par).index(ins)
        for j, ch in enumerate(list(ins)):
            par.insert(i + j, ch)
        par.remove(ins)
    # a paragraph whose mark was deleted merges into the next: for text
    # purposes, one with no remaining text simply disappears
    for p in list(body):
        if p.tag == W + "p" and p.get("_mark_deleted") == "1" and not para_text(p):
            body.remove(p)


def reject_all(root) -> None:
    """Resolve every mark as rejected: insertions vanish, deletions come back."""
    body = _body(root)
    for ins in list(root.iter(W + "ins")):
        par = ins.getparent()
        if par is None:
            continue
        if par.tag == W + "rPr":
            # paragraph-mark insertion rejected: the paragraph itself goes
            p = par.getparent().getparent()
            p.set("_mark_inserted", "1")
            par.remove(ins)
            continue
        par.remove(ins)
    for d in list(root.iter(W + "del")):
        par = d.getparent()
        if par is None:
            continue
        if par.tag == W + "rPr":
            par.remove(d)
            continue
        i = list(par).index(d)
        for j, ch in enumerate(list(d)):
            for t in ch.iter(W + "delText"):
                t.tag = W + "t"
            par.insert(i + j, ch)
        par.remove(d)
    for p in list(body):
        if p.tag == W + "p" and p.get("_mark_inserted") == "1" and not para_text(p):
            body.remove(p)


def _stamp_deleted_marks(root) -> None:
    """Tag paragraphs whose mark is deleted so accept_all can drop them."""
    for p in root.iter(W + "p"):
        ppr = p.find(W + "pPr")
        if ppr is not None and ppr.find(W + "rPr/" + W + "del") is not None:
            p.set("_mark_deleted", "1")


def _strip_private_attrs(root) -> None:
    for p in root.iter(W + "p"):
        for k in ("_mark_deleted", "_mark_inserted"):
            if k in p.attrib:
                del p.attrib[k]


def build_tracked_changes(old_path: str, new_path: str, out_path: str, *,
                          author: str, date: str | None = None) -> dict:
    """Write OUT = NEW with every difference from OLD marked as a revision by
    `author`, then verify: accept-all == NEW, reject-all == OLD (paragraph
    texts). Raises if either fails, so a wrong file is never written."""
    ET = _lxml()
    if not (author or "").strip():
        raise ValueError("author is required — every mark must carry a real name")
    old_p, new_p, out_p = (Path(x).expanduser() for x in (old_path, new_path, out_path))
    for p in (old_p, new_p):
        if not p.is_file():
            raise FileNotFoundError(str(p))
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    old_root = ET.fromstring(_read_document_xml(old_p))
    new_root = ET.fromstring(_read_document_xml(new_p))
    old_texts, new_texts = body_texts(old_root), body_texts(new_root)
    old_paras = [p for p in _body(old_root) if p.tag == W + "p"]
    out_root = copy.deepcopy(new_root)
    out_body = _body(out_root)
    out_paras = [p for p in out_body if p.tag == W + "p"]
    marks = _Marks(ET, author.strip(), date)

    sm = difflib.SequenceMatcher(None, old_texts, new_texts, autojunk=False)
    replaced_whole = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "delete":
            anchor = out_paras[j1] if j1 < len(out_paras) else None
            for k in range(i1, i2):
                dp = _as_deleted_copy(ET, marks, old_paras[k])
                if anchor is not None:
                    anchor.addprevious(dp)
                else:
                    out_body.append(dp)   # after the last paragraph (before sectPr handled below)
            continue
        if op == "insert":
            for k in range(j1, j2):
                _mark_inserted(ET, marks, out_paras[k])
            continue
        # replace: pair old and new paragraphs by SIMILARITY, keeping both
        # documents' order (the pairing is the longest order-preserving run),
        # so an uneven block — two old paragraphs against five new ones — does
        # not pair by position and diff unrelated text. From the reporter's
        # script (feedback 800d9cc0b737), which did it this way from the start.
        pairs = _pair_by_similarity(old_texts, new_texts, i1, i2, j1, j2)
        paired_old = {i for i, _ in pairs}
        paired_new = {j for _, j in pairs}
        for i, j in pairs:
            op_, np_ = old_paras[i], out_paras[j]
            if _has_non_text(op_) or _has_non_text(np_):
                np_.addprevious(_as_deleted_copy(ET, marks, op_))
                _mark_inserted(ET, marks, np_)
                replaced_whole += 1
            else:
                _rebuild_word_diff(ET, marks, np_, old_texts[i], new_texts[j])
        for j in range(j1, j2):
            if j not in paired_new:
                _mark_inserted(ET, marks, out_paras[j])
        for i in range(i1, i2):
            if i in paired_old:
                continue
            # an unpaired old paragraph goes before the next paired new one,
            # else at the end of the block
            nxt = [j for (k, j) in pairs if k > i]
            at = nxt[0] if nxt else j2
            dp = _as_deleted_copy(ET, marks, old_paras[i])
            if at < len(out_paras):
                out_paras[at].addprevious(dp)
            else:
                out_body.append(dp)

    # keep w:sectPr last
    sect = out_body.find(W + "sectPr")
    if sect is not None:
        out_body.remove(sect); out_body.append(sect)

    # --- verify before writing anything ---
    acc = copy.deepcopy(out_root); _stamp_deleted_marks(acc); accept_all(acc)
    rej = copy.deepcopy(out_root); reject_all(rej)
    acc_ok = body_texts(acc) == new_texts
    rej_ok = body_texts(rej) == old_texts
    if not (acc_ok and rej_ok):
        def _first_diff(a, b):
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    return {"index": i, "got": x[:120], "want": y[:120]}
            return {"index": min(len(a), len(b)), "got": None, "want": None,
                    "length": (len(a), len(b))}
        raise RuntimeError(
            "tracked-changes verification failed — nothing written. "
            + ("accept-all != NEW " + str(_first_diff(body_texts(acc), new_texts)) if not acc_ok else "")
            + ("reject-all != OLD " + str(_first_diff(body_texts(rej), old_texts)) if not rej_ok else ""))
    _strip_private_attrs(out_root)

    out_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_p.with_suffix(out_p.suffix + ".tmp")
    with zipfile.ZipFile(new_p) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = ET.tostring(out_root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)
    shutil.move(str(tmp), str(out_p))
    tables = sum(1 for _ in out_body.iter(W + "tbl"))
    return {
        "out_path": str(out_p),
        "author": author.strip(),
        "insertions": marks.ins,
        "deletions": marks.dels,
        "paragraphs_old": len(old_texts),
        "paragraphs_new": len(new_texts),
        "paragraphs_replaced_whole": replaced_whole,
        "tables_from_new_unmarked": tables,
        "verified": {"accept_all_equals_new": True, "reject_all_equals_old": True},
        "not_produced": ["formatting-only revisions", "moved text (shown as delete + insert)",
                         "table-level revisions"],
    }


def verify_tracked_changes(marked_path: str, old_path: str, new_path: str) -> dict:
    """The round-trip on any marked file, ours or LibreOffice's: accept-all
    must equal NEW, reject-all must equal OLD, by body paragraph text."""
    ET = _lxml()
    marked = ET.fromstring(_read_document_xml(Path(marked_path).expanduser()))
    old_texts = body_texts(ET.fromstring(_read_document_xml(Path(old_path).expanduser())))
    new_texts = body_texts(ET.fromstring(_read_document_xml(Path(new_path).expanduser())))
    acc = copy.deepcopy(marked); _stamp_deleted_marks(acc); accept_all(acc)
    rej = copy.deepcopy(marked); reject_all(rej)
    a, r = body_texts(acc), body_texts(rej)
    authors = sorted({e.get(W + "author") or "" for e in marked.iter(W + "ins", W + "del")})
    return {
        "accept_all_equals_new": a == new_texts,
        "reject_all_equals_old": r == old_texts,
        "insertions": sum(1 for _ in marked.iter(W + "ins")),
        "deletions": sum(1 for _ in marked.iter(W + "del")),
        "authors": authors,
        "first_mismatch": None if (a == new_texts and r == old_texts) else {
            "accept": next(((i, x[:80], y[:80]) for i, (x, y) in enumerate(zip(a, new_texts)) if x != y), None),
            "reject": next(((i, x[:80], y[:80]) for i, (x, y) in enumerate(zip(r, old_texts)) if x != y), None),
        },
    }
