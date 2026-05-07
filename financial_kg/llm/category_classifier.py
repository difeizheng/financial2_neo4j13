"""Financial indicator category classifier for hybrid retrieval."""
from __future__ import annotations
import re
from typing import Optional


INDICATOR_CATEGORIES = {
    "收入类": [
        "营业收入",
        "投资收益",
        "营业外收入",
        "销售收入",
        "主营业务收入",
        "其他业务收入",
        "利息收入",
        "股利收入",
    ],
    "成本类": [
        "营业成本",
        "生产成本",
        "直接材料",
        "直接人工",
        "制造费用",
        "主营业务成本",
        "原材料成本",
        "辅助材料成本",
    ],
    "费用类": [
        "管理费用",
        "销售费用",
        "财务费用",
        "营业费用",
        "研发费用",
        "折旧费用",
        "摊销费用",
        "人工费用",
        "办公费用",
        "差旅费用",
    ],
    "利润类": [
        "净利润",
        "毛利润",
        "营业利润",
        "利润总额",
        "EBIT",
        "EBITDA",
        "税前利润",
        "税后利润",
    ],
    "投资类": [
        "总投资",
        "静态投资",
        "动态投资",
        "建设投资",
        "固定资产投资",
        "无形资产投资",
        "股权投资",
        "债权投资",
    ],
    "资产类": [
        "总资产",
        "流动资产",
        "固定资产",
        "无形资产",
        "应收账款",
        "存货",
        "现金及现金等价物",
        "预付账款",
    ],
    "负债类": [
        "总负债",
        "流动负债",
        "长期负债",
        "应付账款",
        "借款",
        "应付工资",
        "应付税费",
        "预收账款",
    ],
    "现金流类": [
        "经营活动现金流",
        "投资活动现金流",
        "筹资活动现金流",
        "自由现金流",
        "净现金流",
        "现金流入",
        "现金流出",
    ],
    "税金类": [
        "所得税",
        "增值税",
        "营业税金",
        "税费合计",
        "城市维护建设税",
        "教育费附加",
        "印花税",
    ],
    "人工成本类": [
        "工资",
        "福利费",
        "社会保险",
        "住房公积金",
        "职工薪酬",
        "人工成本合计",
        "加班费",
        "奖金",
    ],
    "材料成本类": [
        "原材料",
        "辅助材料",
        "包装材料",
        "材料成本合计",
        "采购成本",
        "仓储成本",
    ],
    "折旧摊销类": [
        "固定资产折旧",
        "无形资产摊销",
        "长期待摊费用摊销",
        "累计折旧",
        "累计摊销",
    ],
    "利息费用类": [
        "利息支出",
        "利息收入",
        "利息费用",
        "财务费用-利息",
        "借款利息",
    ],
    "股权类": [
        "股本",
        "资本公积",
        "盈余公积",
        "未分配利润",
        "实收资本",
        "股东权益",
    ],
    "其他类": [
        "其他费用",
        "其他收入",
        "营业外支出",
        "汇兑损益",
        "资产减值损失",
        "坏账准备",
    ],
}

CATEGORY_KEYWORDS = {
    "收入类": ["收入", "营收", "销售额", "收益", "利息收入", "股利"],
    "成本类": ["成本", "生产", "材料", "人工", "制造", "原材料"],
    "费用类": ["费用", "管理", "销售", "财务", "研发", "折旧", "摊销", "办公", "差旅"],
    "利润类": ["利润", "盈利", "毛利", "净利", "EBIT", "EBITDA", "税前", "税后"],
    "投资类": ["投资", "建设", "固定资产", "无形资产", "股权", "债权"],
    "资产类": ["资产", "流动", "固定", "应收", "存货", "现金", "预付"],
    "负债类": ["负债", "借款", "应付", "工资", "税费", "预收"],
    "现金流类": ["现金流", "现金", "自由现金流", "流入", "流出"],
    "税金类": ["税", "税金", "税费", "所得税", "增值税", "城建税", "教育费"],
    "人工成本类": ["工资", "福利", "社保", "公积金", "薪酬", "人工成本", "加班", "奖金"],
    "材料成本类": ["原材料", "辅助材料", "包装", "采购", "仓储"],
    "折旧摊销类": ["折旧", "摊销", "累计折旧", "累计摊销"],
    "利息费用类": ["利息", "利息支出", "利息收入", "借款利息"],
    "股权类": ["股本", "资本公积", "盈余公积", "实收资本", "股东权益"],
    "其他类": ["其他", "营业外", "汇兑", "减值", "坏账"],
}

QUESTION_TYPE_PATTERNS = {
    "数值查询": [
        r"\d{4}年.*是多少",
        r".*是多少",
        r".*金额",
        r".*数值",
        r".*总计",
        r".*合计",
    ],
    "趋势分析": [
        r"趋势",
        r"变化",
        r"增长",
        r"增长率",
        r"变动",
        r"波动",
        r"近\d+年",
    ],
    "对比分析": [
        r"对比",
        r"比较",
        r"差异",
        r"差别",
        r"不同",
        r"vs",
        r" versus ",
    ],
    "因果分析": [
        r"影响",
        r"依赖",
        r"原因",
        r"导致",
        r"关联",
        r"关系",
        r"计算",
    ],
    "占比分析": [
        r"占比",
        r"比例",
        r"百分比",
        r"构成",
        r"结构",
    ],
}

KEYWORD_WEIGHTS = {
    "总计": 0.3,
    "合计": 0.3,
    "总额": 0.3,
    "增长率": 0.2,
    "占比": 0.2,
    "比例": 0.2,
    "变化": 0.15,
    "差异": 0.15,
}


def extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from question text."""
    stopwords = {"的", "是", "多少", "什么", "有", "在", "和", "与", "或", "吗", "呢", "啊"}
    
    tokens = re.findall(r"[a-zA-Z]+|\d+|[\u4e00-\u9fa5]{2,}", text)
    
    keywords = []
    for token in tokens:
        token_lower = token.lower()
        if token_lower not in stopwords and len(token) >= 2:
            keywords.append(token)
    
    year_pattern = re.findall(r"\d{4}", text)
    short_year_pattern = re.findall(r"\d{2,3}", text)
    
    inferred_years = []
    for year in year_pattern:
        keywords.append(year)
        inferred_years.append(year)
    
    for short_year in short_year_pattern:
        if len(short_year) == 2 or len(short_year) == 3:
            try:
                short_int = int(short_year)
                if 20 <= short_int <= 99:
                    inferred_year = f"20{short_int}"
                    if inferred_year not in inferred_years:
                        keywords.append(inferred_year)
                        inferred_years.append(inferred_year)
                elif 200 <= short_int <= 999:
                    inferred_year = f"{short_int}0"
                    if inferred_year not in inferred_years:
                        keywords.append(inferred_year)
                        inferred_years.append(inferred_year)
            except ValueError:
                pass
    
    for weight_kw in KEYWORD_WEIGHTS:
        if weight_kw in text:
            keywords.append(weight_kw)
    
    return keywords


def classify_category(question: str) -> Optional[str]:
    """Classify question into financial indicator category."""
    question_lower = question.lower()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in question_lower or kw in question:
                return category
    
    return None


def classify_question_type(question: str) -> str:
    """Classify question type (数值查询/趋势分析/对比分析等)."""
    for q_type, patterns in QUESTION_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, question, re.IGNORECASE):
                return q_type
    
    return "通用查询"


def match_indicator_category(indicator_name: str) -> Optional[str]:
    """Match indicator name to predefined category."""
    for category, indicators in INDICATOR_CATEGORIES.items():
        for ind_name in indicators:
            if ind_name in indicator_name or indicator_name in ind_name:
                return category
    
    return None


def calculate_keyword_match_score(question: str, indicator_name: str, keywords: list[str]) -> float:
    """Calculate keyword match score between question and indicator."""
    score = 0.0
    
    for kw in keywords:
        if kw in indicator_name:
            base_score = 0.5
            
            if kw in KEYWORD_WEIGHTS:
                base_score += KEYWORD_WEIGHTS[kw]
            
            if kw == indicator_name or kw in indicator_name.split():
                base_score += 0.2
            
            score += base_score
    
    return min(score, 1.0)


def get_category_indicators(category: str) -> list[str]:
    """Get all indicator names for a given category."""
    return INDICATOR_CATEGORIES.get(category, [])