import re
from astra.core.logger import get_logger
from astra.models.task_analysis import TaskAnalysis, TaskType

logger = get_logger("astra.context.task_analyzer")

TYPE_PATTERNS = [
    (TaskType.BUG_FIX, re.compile(r"\b(fix|bug|crash|error|exception|fail|broken|issue|defect|regression|traceback)\b", re.I)),
    (TaskType.FEATURE_ADDITION, re.compile(r"\b(add|create|implement|build|new|feature|support|introduce|generate)\b", re.I)),
    (TaskType.REFACTOR, re.compile(r"\b(refactor|restructure|reorganize|clean|simplify|extract|move|rename|consolidate)\b", re.I)),
    (TaskType.OPTIMIZATION, re.compile(r"\b(optimi[sz]e|speed|performance|fast|slow|memory|cache|throughput|latency|scale)\b", re.I)),
    (TaskType.DEBUG_TRACE, re.compile(r"\b(debug|trace|investigate|why|root cause|propagat|where does|how does)\b", re.I)),
    (TaskType.ARCHITECTURE_REVIEW, re.compile(r"\b(architect|design|layer|boundary|structure|review|assess|evaluate|audit)\b", re.I)),
    (TaskType.ANALYSIS, re.compile(r"\b(analy[sz]e|understand|explain|what|describe|overview|summari[sz]e|map)\b", re.I)),
]

DOMAIN_PATTERNS = [
    (re.compile(r"\b(auth|login|password|token|session|jwt|oauth|credential|user)\b", re.I), "authentication"),
    (re.compile(r"\b(storage|database|persist|schema|migration|repo|model)\b", re.I), "data"),
    (re.compile(r"\b(api|endpoint|route|controller|handler|request|response)\b", re.I), "api"),
    (re.compile(r"\b(scan|parse|reader|index|graph|knowledge|semantic)\b", re.I), "knowledge"),
    (re.compile(r"\b(dashboard|frontend|view|template|ui|render)\b", re.I), "presentation"),
    (re.compile(r"\b(config|setting|env|constant|flag)\b", re.I), "configuration"),
    (re.compile(r"\b(scan|file|repo|repository|directory|tree)\b", re.I), "filesystem"),
]

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "i", "we", "you", "they", "it",
    "to", "of", "in", "on", "at", "for", "with", "by", "from",
    "and", "or", "but", "not", "if", "then", "so", "as",
    "do", "does", "did", "will", "would", "should", "could", "may", "might",
    "my", "our", "your", "their", "its", "his", "her",
    "what", "which", "who", "whom", "whose", "where", "why", "how",
    "there", "here", "when", "while", "during",
    # Question scaffolding, not subject matter. "how does ranking work" is
    # about ranking; treating "work" and "does" as terms sent the ranker looking
    # for files that merely use the word.
    "work", "works", "working", "worked", "used", "using", "uses",
    "get", "gets", "make", "makes", "made", "take", "takes",
    "file", "files", "code", "thing", "things", "stuff",
    "done", "via", "per", "etc", "one", "two",
}


class TaskAnalyzer:
    def analyze(self, task_text):
        task_type = self._detect_type(task_text)
        keywords = self._extract_keywords(task_text)
        domain = self._detect_domain(task_text, keywords)
        scope = self._extract_scope(keywords)
        confidence = self._compute_confidence(task_type, keywords, domain)
        return TaskAnalysis(
            task=task_text,
            task_type=task_type,
            target_scope=scope,
            affected_domain=domain,
            keywords=keywords,
            confidence=confidence,
        )

    def _detect_type(self, text):
        scores = {}
        for ttype, pattern in TYPE_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                scores[ttype] = len(matches)
        if not scores:
            return TaskType.ANALYSIS
        return max(scores.items(), key=lambda kv: kv[1])[0]

    def _extract_keywords(self, text):
        raw = re.findall(r"[A-Za-z_][A-Za-z0-9_/.\\-]+", text)
        keywords = []
        seen = set()
        for token in raw:
            low = token.lower()
            if low in STOPWORDS:
                continue
            if len(low) <= 2:
                continue
            if low in seen:
                continue
            seen.add(low)
            keywords.append(token)
        return keywords

    def _detect_domain(self, text, keywords):
        combined = " ".join([text] + keywords).lower()
        scores = {}
        for pattern, domain in DOMAIN_PATTERNS:
            matches = pattern.findall(combined)
            if matches:
                scores[domain] = scores.get(domain, 0) + len(matches)
        if not scores:
            return ""
        return max(scores.items(), key=lambda kv: kv[1])[0]

    def _extract_scope(self, keywords):
        scope = []
        for kw in keywords:
            norm = kw.replace("\\", "/").replace(".py", "").replace(".js", "").replace(".ts", "")
            if "/" in norm or "." in norm:
                scope.append(norm)
        return scope

    def _compute_confidence(self, task_type, keywords, domain):
        conf = 0.4
        if task_type != TaskType.ANALYSIS:
            conf += 0.25
        if keywords:
            conf += min(0.2, len(keywords) * 0.04)
        if domain:
            conf += 0.15
        return round(min(conf, 1.0), 2)
