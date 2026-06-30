"""
TalentIQ - JobIntel Simulator
Python port of the original JobIntel Agent's data generation logic.
Generates realistic simulated job market data for any country/domain combination.
Used when Adzuna API returns insufficient results or as primary data source.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

# ── COMPANY DATA ──────────────────────────────────────────────────────────────

COMPANY_DATA = {
    "Australia": {
        "Banking & Financial Services": {
            "companies": ["Commonwealth Bank","Westpac","ANZ","NAB","Macquarie Bank","Suncorp","QBE Insurance","IAG","AMP Limited","Bendigo Bank"],
            "types": {"Commonwealth Bank":"Banking","Westpac":"Banking","ANZ":"Banking","NAB":"Banking","Macquarie Bank":"Investment Banking","Suncorp":"Banking & Insurance","QBE Insurance":"Insurance","IAG":"Insurance","AMP Limited":"Super & Insurance","Bendigo Bank":"Banking"}
        },
        "Healthcare": {
            "companies": ["Ramsay Health Care","Healius","Sonic Healthcare","CSL Limited","Cochlear","ResMed","Medibank","Bupa Australia","HCF","NIB Health"],
            "types": {"Ramsay Health Care":"Healthcare Provider","Healius":"Medical Services","Sonic Healthcare":"Pathology","CSL Limited":"Biotechnology","Cochlear":"Medical Technology","ResMed":"Medical Equipment","Medibank":"Health Insurance","Bupa Australia":"Health Insurance","HCF":"Health Insurance","NIB Health":"Health Insurance"}
        },
        "Technology": {
            "companies": ["Atlassian","Canva","Afterpay","Xero","REA Group","Seek Limited","WiseTech Global","TechnologyOne","Computershare","NextDC"],
            "types": {"Atlassian":"Software","Canva":"Software","Afterpay":"Fintech","Xero":"Software","REA Group":"Technology","Seek Limited":"Technology","WiseTech Global":"Software","TechnologyOne":"Software","Computershare":"Technology Services","NextDC":"Data Centers"}
        },
        "Government": {
            "companies": ["Department of Finance","ATO","Department of Defence","Department of Health","Services Australia","ABS","Department of Education","Department of Infrastructure"],
            "types": {"Department of Finance":"Government","ATO":"Government","Department of Defence":"Government","Department of Health":"Government","Services Australia":"Government","ABS":"Government","Department of Education":"Government","Department of Infrastructure":"Government"}
        },
        "Accounting & Audit": {
            "companies": ["Deloitte Australia","PwC Australia","EY Australia","KPMG Australia","Grant Thornton","BDO Australia","RSM Australia","Pitcher Partners","William Buck","Hall Chadwick"],
            "types": {"Deloitte Australia":"Big 4","PwC Australia":"Big 4","EY Australia":"Big 4","KPMG Australia":"Big 4","Grant Thornton":"Mid-Tier","BDO Australia":"Mid-Tier","RSM Australia":"Mid-Tier","Pitcher Partners":"Mid-Tier","William Buck":"Boutique","Hall Chadwick":"Boutique"}
        },
        "Retail": {
            "companies": ["Woolworths","Coles","Wesfarmers","Harvey Norman","JB Hi-Fi","Myer","David Jones","Kmart","Bunnings","Officeworks"],
            "types": {"Woolworths":"Supermarket","Coles":"Supermarket","Wesfarmers":"Conglomerate","Harvey Norman":"Electronics","JB Hi-Fi":"Electronics","Myer":"Department Store","David Jones":"Department Store","Kmart":"Discount Retail","Bunnings":"Hardware","Officeworks":"Office Supplies"}
        },
        "Mining & Resources": {
            "companies": ["BHP","Rio Tinto","Fortescue Metals","Newcrest Mining","Woodside Energy","Santos","Oil Search","South32","IGO Limited","Pilbara Minerals"],
            "types": {"BHP":"Diversified Mining","Rio Tinto":"Diversified Mining","Fortescue Metals":"Iron Ore","Newcrest Mining":"Gold","Woodside Energy":"LNG","Santos":"Oil & Gas","Oil Search":"Oil & Gas","South32":"Diversified Mining","IGO Limited":"Battery Minerals","Pilbara Minerals":"Lithium"}
        },
        "Education": {
            "companies": ["University of Melbourne","University of Sydney","ANU","Monash University","UNSW","QUT","RMIT University","UTS","Deakin University","Macquarie University"],
            "types": {"University of Melbourne":"University","University of Sydney":"University","ANU":"University","Monash University":"University","UNSW":"University","QUT":"University","RMIT University":"University","UTS":"University","Deakin University":"University","Macquarie University":"University"}
        },
    },
    "USA": {
        "Technology": {
            "companies": ["Google","Microsoft","Amazon","Apple","Meta","Netflix","Tesla","Salesforce","Oracle","IBM"],
            "types": {"Google":"Tech Giant","Microsoft":"Tech Giant","Amazon":"Tech Giant","Apple":"Tech Giant","Meta":"Social Media","Netflix":"Streaming","Tesla":"EV & Tech","Salesforce":"SaaS","Oracle":"Enterprise Software","IBM":"IT Services"}
        },
        "Banking & Financial Services": {
            "companies": ["JPMorgan Chase","Goldman Sachs","Morgan Stanley","Bank of America","Citigroup","Wells Fargo","BlackRock","Fidelity","Charles Schwab","American Express"],
            "types": {"JPMorgan Chase":"Banking","Goldman Sachs":"Investment Banking","Morgan Stanley":"Investment Banking","Bank of America":"Banking","Citigroup":"Banking","Wells Fargo":"Banking","BlackRock":"Asset Management","Fidelity":"Asset Management","Charles Schwab":"Brokerage","American Express":"Financial Services"}
        },
        "Healthcare": {
            "companies": ["Johnson & Johnson","Pfizer","UnitedHealth Group","CVS Health","Anthem","Humana","Abbott","Medtronic","Becton Dickinson","Baxter International"],
            "types": {"Johnson & Johnson":"Pharma","Pfizer":"Pharma","UnitedHealth Group":"Health Insurance","CVS Health":"Pharmacy","Anthem":"Health Insurance","Humana":"Health Insurance","Abbott":"Medical Devices","Medtronic":"Medical Devices","Becton Dickinson":"Medical Devices","Baxter International":"Medical Products"}
        },
        "Government": {
            "companies": ["Department of Treasury","Federal Reserve","IRS","Department of Defense","Department of Homeland Security","CDC","Department of Veterans Affairs","SSA"],
            "types": {"Department of Treasury":"Federal Government","Federal Reserve":"Central Bank","IRS":"Government","Department of Defense":"Government","Department of Homeland Security":"Government","CDC":"Government","Department of Veterans Affairs":"Government","SSA":"Government"}
        },
    },
    "UK": {
        "Banking & Financial Services": {
            "companies": ["Barclays","HSBC","Lloyds Banking Group","NatWest","Standard Chartered","Santander UK","Nationwide","TSB Bank","Monzo","Revolut"],
            "types": {"Barclays":"Banking","HSBC":"Banking","Lloyds Banking Group":"Banking","NatWest":"Banking","Standard Chartered":"Banking","Santander UK":"Banking","Nationwide":"Building Society","TSB Bank":"Banking","Monzo":"Neobank","Revolut":"Fintech"}
        },
        "Technology": {
            "companies": ["DeepMind","ARM Holdings","Sage Group","Ocado","Autotrader","Just Eat","Deliveroo","Darktrace","Babylon Health","Wise"],
            "types": {"DeepMind":"AI Research","ARM Holdings":"Semiconductors","Sage Group":"Accounting Software","Ocado":"E-commerce","Autotrader":"Marketplace","Just Eat":"Food Delivery","Deliveroo":"Food Delivery","Darktrace":"Cybersecurity","Babylon Health":"HealthTech","Wise":"Fintech"}
        },
    },
    "India": {
        "Technology": {
            "companies": ["TCS","Infosys","Wipro","HCL Technologies","Tech Mahindra","Cognizant India","Capgemini India","Mindtree","Mphasis","Hexaware"],
            "types": {"TCS":"IT Services","Infosys":"IT Services","Wipro":"IT Services","HCL Technologies":"IT Services","Tech Mahindra":"IT Services","Cognizant India":"IT Services","Capgemini India":"IT Services","Mindtree":"IT Services","Mphasis":"IT Services","Hexaware":"IT Services"}
        },
        "Banking & Financial Services": {
            "companies": ["HDFC Bank","ICICI Bank","SBI","Axis Bank","Kotak Mahindra","IndusInd Bank","Yes Bank","RBL Bank","Federal Bank","IDFC First"],
            "types": {"HDFC Bank":"Banking","ICICI Bank":"Banking","SBI":"PSU Banking","Axis Bank":"Banking","Kotak Mahindra":"Banking","IndusInd Bank":"Banking","Yes Bank":"Banking","RBL Bank":"Banking","Federal Bank":"Banking","IDFC First":"Banking"}
        },
    },
    "Canada": {
        "Banking & Financial Services": {
            "companies": ["RBC","TD Bank","Scotiabank","BMO","CIBC","Manulife","Sun Life","Great-West Lifeco","Desjardins","ATB Financial"],
            "types": {"RBC":"Banking","TD Bank":"Banking","Scotiabank":"Banking","BMO":"Banking","CIBC":"Banking","Manulife":"Insurance","Sun Life":"Insurance","Great-West Lifeco":"Insurance","Desjardins":"Credit Union","ATB Financial":"Banking"}
        },
        "Technology": {
            "companies": ["Shopify","BlackBerry","OpenText","CGI Group","Constellation Software","Descartes Systems","Kinaxis","D2L","Hootsuite","Slack Canada"],
            "types": {"Shopify":"E-commerce","BlackBerry":"Security Software","OpenText":"Enterprise Software","CGI Group":"IT Services","Constellation Software":"Vertical Software","Descartes Systems":"Logistics Tech","Kinaxis":"Supply Chain","D2L":"EdTech","Hootsuite":"Social Media","Slack Canada":"Collaboration"}
        },
    },
}

# ── SKILLS DATABASE ───────────────────────────────────────────────────────────

SKILLS_DB = {
    "Banking & Financial Services": ["Credit Risk Management","Basel III","APRA Compliance","AML/CTF","KYC","Financial Modeling","Portfolio Management","Investment Analysis","Regulatory Reporting","Stress Testing","Capital Management","Liquidity Risk","Market Risk","Operational Risk","Derivatives Trading"],
    "Healthcare": ["Clinical Research","Medical Device Regulations","Healthcare Analytics","Patient Safety","EMR/EHR Systems","Clinical Trials","Drug Safety","Pharmacovigilance","Medical Coding","Health Economics"],
    "Technology": ["Software Development","Cloud Architecture","DevOps","Machine Learning","Data Engineering","Cybersecurity","API Design","Microservices","System Design","Agile Methodology"],
    "Government": ["Policy Analysis","Regulatory Compliance","Stakeholder Management","Project Management","Budget Management","Risk Assessment","Data Governance","Public Administration","Grant Management","Procurement"],
    "Accounting & Audit": ["Financial Reporting","IFRS","GAAP","Tax Compliance","Audit","BAS/GST","Payroll","Bookkeeping","Reconciliation","Xero","MYOB","SAP","Oracle Financials"],
    "Retail": ["Category Management","Inventory Management","Supply Chain","Merchandising","Customer Experience","Retail Analytics","Pricing Strategy","Vendor Management","E-commerce","Loss Prevention"],
    "Mining & Resources": ["Geological Mapping","Mine Planning","Ore Reserve Estimation","Environmental Compliance","Safety Management","Mineral Processing","Geotechnical Engineering","Tailings Management","Drilling Operations","Resource Modeling"],
    "Education": ["Curriculum Development","Assessment Design","Learning Management Systems","Student Engagement","Research Skills","Academic Writing","ATAR","TEQSA Compliance","Online Learning","Student Wellbeing"],
}

TOOLS_DB = {
    "Banking & Financial Services": ["Bloomberg Terminal","Murex","Finastra","Temenos","FIS Global","SS&C","Misys","Calypso","SAS Risk","Oracle FLEXCUBE"],
    "Healthcare": ["Epic","Cerner","Meditech","Allscripts","eClinicalWorks","Veeva","CTMS","SAS Clinical","IBM Watson Health","Salesforce Health Cloud"],
    "Technology": ["AWS","Azure","GCP","Kubernetes","Docker","Jenkins","Terraform","Python","Java","React","Node.js","PostgreSQL","MongoDB","Kafka","Spark"],
    "Government": ["SAP","Oracle ERP","Microsoft SharePoint","Salesforce Government","ServiceNow","Tableau","Power BI","GovCMS","AWS GovCloud","JIRA"],
    "Accounting & Audit": ["Xero","MYOB","QuickBooks","SAP","Oracle Financials","CaseWare","CCH ProSystem","Reckon","Sage","FreshBooks"],
    "Retail": ["SAP Retail","Oracle Retail","Manhattan Associates","JDA","Relex","Blue Yonder","Microsoft Dynamics","Shopify","Magento","Salesforce Commerce"],
    "Mining & Resources": ["Vulcan","Surpac","Datamine","Leapfrog","AutoCAD","ArcGIS","MINEMAX","Whittle","SiteAdvisor","Promine"],
    "Education": ["Canvas","Blackboard","Moodle","D2L","Microsoft Teams","Zoom","Turnitin","PowerSchool","Ellucian","Anthology"],
}

CERTS_DB = {
    "Banking & Financial Services": ["CFA Level I/II/III","FRM","CPA","CFP","CAIA","PRM","ACCA","CA ANZ","FINSIA","CPA Australia"],
    "Healthcare": ["AHPRA","RN","MD","PhD","ClinicalTrials.gov GCP","ISO 13485","TGA","FDA 21 CFR Part 11","ACHS","JCI Accreditation"],
    "Technology": ["AWS Certified Solutions Architect","Azure Administrator","Google Cloud Professional","Certified Kubernetes Administrator","PMP","Scrum Master (CSM)","CISSP","TOGAF","ITIL","CompTIA Security+"],
    "Government": ["IPAA","Prince2","PMP","PRINCE2","AGSVA Security Clearance","ISO 27001","CIPP","Lean Six Sigma","Certificate IV in Government","APS Leadership"],
    "Accounting & Audit": ["CPA Australia","CA ANZ","ACCA","CMA","Xero Certified","MYOB Certified","CIA","CFE","Tax Agent Registration","BAS Agent Registration"],
    "Retail": ["Retail Ready Training","PMP","Six Sigma","Lean","Supply Chain Management Professional","CPIM","CLTD","Shopify Certified Partner","Google Analytics","Salesforce Certified"],
    "Mining & Resources": ["MSHA","Site Senior Executive (SSE)","Mine Manager Certificate","ISO 14001","ICMM","First Aid","Explosives Handler","WHS","CPEng","RPEng"],
    "Education": ["Teaching Registration (AITSL)","Graduate Certificate Education","Master of Education","PhD","TESOL","CPD Hours","ASQA","Higher Education Standards","PhD Supervision","ARC Grant"],
}

FUNCTIONS_DB = {
    "Banking & Financial Services": ["Risk Management","Compliance","Investment Banking","Retail Banking","Wealth Management","Operations","Finance","Audit","Technology","Strategy"],
    "Healthcare": ["Clinical Operations","Medical Affairs","Regulatory","Quality Assurance","Research & Development","Finance","IT","Administration","Patient Services","Supply Chain"],
    "Technology": ["Software Engineering","Data Science","Product Management","DevOps","Security","Architecture","QA/Testing","Agile/Scrum","UX/UI","Support"],
    "Government": ["Policy","Finance","Operations","HR","ICT","Audit","Legal","Procurement","Communications","Program Management"],
    "Accounting & Audit": ["Audit","Tax","Advisory","Bookkeeping","Payroll","Financial Reporting","Management Accounting","Forensic Accounting","Corporate Finance","Treasury"],
    "Retail": ["Buying","Merchandising","Store Operations","E-commerce","Supply Chain","Finance","HR","Marketing","Loss Prevention","Customer Experience"],
    "Mining & Resources": ["Geology","Mine Engineering","Environment & Sustainability","Safety","Processing","Maintenance","Finance","HR","Community Relations","Projects"],
    "Education": ["Teaching","Research","Administration","Student Services","Finance","IT","Library","Marketing","International","Quality Assurance"],
}

TITLES_DB = {
    "Banking & Financial Services": ["Risk Analyst","Credit Officer","Compliance Manager","Financial Analyst","Investment Manager","Relationship Manager","Branch Manager","Operations Analyst","Treasury Manager","Audit Manager"],
    "Healthcare": ["Clinical Manager","Medical Officer","Nurse Practitioner","Healthcare Analyst","Compliance Officer","Clinical Research Associate","Medical Writer","Pharmacovigilance Specialist","Health Economist","Quality Manager"],
    "Technology": ["Software Engineer","Senior Developer","Cloud Architect","Data Engineer","DevOps Engineer","Security Engineer","Product Manager","Scrum Master","UX Designer","Data Scientist"],
    "Government": ["Policy Analyst","Program Manager","Finance Officer","Project Manager","Communications Officer","ICT Manager","Procurement Officer","HR Business Partner","Audit Manager","EL1 / EL2 Manager"],
    "Accounting & Audit": ["Accountant","Senior Accountant","Audit Manager","Tax Consultant","Financial Controller","CFO","Bookkeeper","Payroll Officer","Management Accountant","Finance Business Partner"],
    "Retail": ["Category Manager","Merchandise Planner","Store Manager","E-commerce Manager","Supply Chain Analyst","Buyer","Operations Manager","Customer Experience Manager","Loss Prevention Officer","Finance Manager"],
    "Mining & Resources": ["Mine Engineer","Geologist","Environmental Officer","Safety Manager","Processing Engineer","Maintenance Manager","Mine Planner","Resource Geologist","Metallurgist","Project Manager"],
    "Education": ["Lecturer","Senior Lecturer","Associate Professor","Professor","Student Advisor","Curriculum Developer","Research Fellow","Dean","Registrar","Learning Designer"],
}

LOCATIONS_DB = {
    "Australia": ["Sydney CBD","Melbourne CBD","Brisbane CBD","Perth CBD","Adelaide CBD","Canberra ACT","Gold Coast QLD","Newcastle NSW","Wollongong NSW","Parramatta NSW","North Sydney","St Kilda Road VIC","Docklands VIC","Fortitude Valley QLD","Subiaco WA"],
    "USA": ["New York NY","San Francisco CA","Chicago IL","Los Angeles CA","Boston MA","Seattle WA","Austin TX","Denver CO","Atlanta GA","Washington DC","Dallas TX","Miami FL","Minneapolis MN","Phoenix AZ","San Jose CA"],
    "UK": ["London EC","Manchester","Birmingham","Leeds","Edinburgh","Bristol","Liverpool","Glasgow","Cardiff","Nottingham","Sheffield","Newcastle","Southampton","Reading","Brighton"],
    "India": ["Bengaluru","Mumbai","Hyderabad","Pune","Chennai","Delhi NCR","Kolkata","Ahmedabad","Noida","Gurgaon","Chandigarh","Coimbatore","Jaipur","Kochi","Indore"],
    "Canada": ["Toronto ON","Vancouver BC","Montreal QC","Calgary AB","Edmonton AB","Ottawa ON","Winnipeg MB","Halifax NS","Quebec City QC","Mississauga ON","Brampton ON","Surrey BC","Hamilton ON","Kitchener ON","London ON"],
}

SOFT_SKILLS = ["Leadership","Communication","Problem Solving","Analytical Thinking","Team Collaboration","Stakeholder Management","Adaptability","Critical Thinking","Attention to Detail","Time Management","Negotiation","Emotional Intelligence","Presentation Skills","Conflict Resolution","Strategic Thinking"]

JOB_PORTALS = ["LinkedIn","Indeed","Glassdoor","Company Career Portal","Monster","Seek","CareerBuilder","ZipRecruiter","Jora","Adzuna"]
EXP_LEVELS = ["Junior","Mid-Level","Senior","Principal","Director"]
EXP_YEARS = ["1-2","2-3","3-5","5-7","7-10","10+"]
JOB_TYPES = ["Full-time","Contract","Part-time","Casual"]

SALARY_RANGES = {
    "Junior": (55000, 85000),
    "Mid-Level": (85000, 120000),
    "Senior": (120000, 160000),
    "Principal": (150000, 200000),
    "Director": (180000, 250000),
}


def _random_date(days_back: int = 30) -> str:
    d = datetime.now() - timedelta(days=random.randint(0, days_back))
    return d.strftime("%Y-%m-%d")


def _pick(lst: list, n: int = 1) -> Any:
    if not lst:
        return None if n == 1 else []
    sample = random.sample(lst, min(n, len(lst)))
    return sample[0] if n == 1 else sample


def _get_domain_data(country: str, domain: str) -> tuple:
    """Return (companies, company_types, locations) for country+domain."""
    country_data = COMPANY_DATA.get(country, COMPANY_DATA.get("Australia", {}))
    # Try exact domain, then partial match, then first available
    domain_data = country_data.get(domain)
    if not domain_data:
        for key in country_data:
            if domain.lower() in key.lower() or key.lower() in domain.lower():
                domain_data = country_data[key]
                break
    if not domain_data:
        domain_data = list(country_data.values())[0] if country_data else {
            "companies": ["Company A","Company B","Company C"],
            "types": {}
        }
    companies = domain_data["companies"]
    types = domain_data["types"]
    locations = LOCATIONS_DB.get(country, LOCATIONS_DB["Australia"])
    return companies, types, locations


def _job_group(title: str) -> str:
    """Categorize a job title into a group label, mirroring the reference output."""
    t = title.lower()
    if "compliance" in t:
        return "Compliance Management Roles"
    if "anti-money" in t or "aml" in t:
        return "Anti-Money Laundering Roles"
    if "credit risk" in t:
        return "Credit Risk Roles"
    if "investment banking" in t:
        return "Investment Banking Roles"
    if "corporate banking" in t:
        return "Corporate Banking Roles"
    if "business banking" in t or "advisor" in t:
        return "Business Banking Roles"
    if "treasury" in t:
        return "Treasury Roles"
    if "wealth management" in t:
        return "Wealth Management Roles"
    if "insurance underwriter" in t:
        return "Insurance Underwriter Roles"
    if "portfolio" in t:
        return "Portfolio Roles"
    if "risk management" in t:
        return "Risk Management Roles"
    if "financial planning" in t:
        return "Financial Planning Roles"
    return "General Roles"


def simulate_jobs(country: str, domain: str, count: int = 100) -> List[Dict[str, Any]]:
    """
    Generate count simulated job records for the given country and domain.
    Mirrors the original JobIntel Agent's generateMockJobData function.
    """
    companies, company_types, locations = _get_domain_data(country, domain)
    skills = SKILLS_DB.get(domain, SKILLS_DB.get("Technology", []))
    tools = TOOLS_DB.get(domain, TOOLS_DB.get("Technology", []))
    certs = CERTS_DB.get(domain, CERTS_DB.get("Technology", []))
    functions = FUNCTIONS_DB.get(domain, FUNCTIONS_DB.get("Technology", []))
    titles = TITLES_DB.get(domain, TITLES_DB.get("Technology", []))

    jobs = []
    for i in range(count):
        company = _pick(companies)
        exp_level = _pick(EXP_LEVELS)
        sal_range = SALARY_RANGES.get(exp_level, (80000, 130000))
        salary_min = random.randint(sal_range[0], (sal_range[0] + sal_range[1]) // 2)
        salary_max = random.randint((sal_range[0] + sal_range[1]) // 2, sal_range[1])
        title = _pick(titles)

        jobs.append({
            "title": title,
            "job_group": _job_group(title),
            "company": company,
            "company_type": company_types.get(company, "Organisation"),
            "location": _pick(locations),
            "domain": domain,
            "job_type": _pick(JOB_TYPES),
            "experience_level": exp_level,
            "experience_years": _pick(EXP_YEARS),
            "key_skills": _pick(skills, min(5, len(skills))),
            "soft_skills": _pick(SOFT_SKILLS, 4),
            "tools_technologies": _pick(tools, min(4, len(tools))),
            "certifications": _pick(certs, min(2, len(certs))),
            "working_function": _pick(functions),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "date_posted": _random_date(30),
            "source": _pick(JOB_PORTALS),
            "source_url": f"https://example.com/jobs/{domain.lower().replace(' ','-')}/{i+1}",
            "education_required": "Bachelor's degree in relevant field, Master's preferred",
        })

    return jobs


def analyse_simulated_jobs(jobs: List[Dict]) -> Dict[str, Any]:
    """Compute analytics from simulated jobs — mirrors original clusterJobs + AnalyticsMetrics."""
    from collections import Counter

    total = len(jobs)
    if not total:
        return {}

    # Skill frequency
    all_skills = []
    for j in jobs:
        all_skills.extend(j.get("key_skills", []))
    skill_counts = Counter(all_skills).most_common(20)
    top_skills = [{"skill": s, "count": c} for s, c in skill_counts]

    # Tools frequency
    all_tools = []
    for j in jobs:
        all_tools.extend(j.get("tools_technologies", []))
    tool_counts = Counter(all_tools).most_common(15)
    top_tools = [{"tool": t, "count": c} for t, c in tool_counts]

    # Salary stats
    salaries = [j.get("salary_min", 0) for j in jobs if j.get("salary_min")]
    salary_stats = {
        "avg": round(sum(salaries) / len(salaries)) if salaries else 0,
        "min": min(salaries) if salaries else 0,
        "max": max(salaries) if salaries else 0,
    }

    # Breakdowns
    job_type_breakdown = dict(Counter(j.get("job_type", "Unknown") for j in jobs))
    company_type_breakdown = dict(Counter(j.get("company_type", "Unknown") for j in jobs).most_common(8))
    exp_level_breakdown = dict(Counter(j.get("experience_level", "Unknown") for j in jobs))
    function_breakdown = dict(Counter(j.get("working_function", "Unknown") for j in jobs).most_common(10))
    location_breakdown = dict(Counter(j.get("location", "Unknown") for j in jobs).most_common(10))
    source_breakdown = dict(Counter(j.get("source", "Unknown") for j in jobs))

    return {
        "total_jobs": total,
        "top_skills": top_skills,
        "top_tools": top_tools,
        "salary_stats": salary_stats,
        "job_type_breakdown": job_type_breakdown,
        "company_type_breakdown": company_type_breakdown,
        "exp_level_breakdown": exp_level_breakdown,
        "function_breakdown": function_breakdown,
        "location_breakdown": location_breakdown,
        "source_breakdown": source_breakdown,
    }