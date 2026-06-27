import requests
import re
import base64
import json
import time
import asyncio
import aiohttp
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- 配置 ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
SEARCH_KEYWORDS = ["vmess", "vless", "trojan", "ss", "ssr"]
MAX_REPOS_PER_KEYWORD = 5
MAX_WORKERS = 20
OUTPUT_FILE = "newlinks.txt"
NODE_TEST_TIMEOUT = 2

# --- 网络配置 ---
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=retries)
session.mount("https://", adapter)
if GITHUB_TOKEN:
    session.headers.update({'Authorization': f'token {GITHUB_TOKEN}'})

# --- 正则与存储 ---
PROTOCOL_PATTERNS = {proto: re.compile(rf"{proto}[^\s\'\"<>\[\]\(\{{}}]+") 
                     for proto in ['vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://']}

# 使用简单的线程安全集合 (使用同步访问)
nodes_found = set()
nodes_lock = asyncio.Lock()

def get_repo_files_bulk(repo_name):
    """使用 Git Trees API 一次性获取仓库文件列表"""
    url = f"https://api.github.com/repos/{repo_name}/git/trees/main?recursive=1"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            tree = resp.json().get('tree', [])
            return [f"https://raw.githubusercontent.com/{repo_name}/main/{item['path']}" 
                    for item in tree if item['type'] == 'blob' and 
                    any(ext in item['path'].lower() for ext in ['.txt', '.md', '.json', 'sub', 'node'])]
    except:
        pass
    return []

async def fetch_and_extract(session, url):
    """异步下载并提取节点"""
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200: return
            content = await resp.text()
            
            # 提取
            found = set()
            for proto, pattern in PROTOCOL_PATTERNS.items():
                found.update(pattern.findall(content))
            
            # B64 尝试
            if len(content) > 50 and not any(p in content for p in PROTOCOL_PATTERNS.keys()):
                try:
                    decoded = base64.b64decode(content).decode('utf-8', errors='ignore')
                    for proto, pattern in PROTOCOL_PATTERNS.items():
                        found.update(pattern.findall(decoded))
                except: pass
            
            async with nodes_lock:
                nodes_found.update(found)
    except: pass

def parse_node(node_link):
    """尝试解析节点获取 host:port"""
    try:
        if node_link.startswith('vmess://'):
            data = json.loads(base64.b64decode(node_link[8:]).decode('utf-8', 'ignore'))
            return data.get('add'), int(data.get('port', 443))
        elif node_link.startswith(('vless://', 'trojan://')):
            u = urlparse(node_link)
            return u.hostname, u.port or 443
        elif node_link.startswith('ss://'):
            host, port = node_link.split('@')[1].split('#')[0].rsplit(':', 1)
            return host, int(port)
    except: return None
    return None

async def check_latency(node, session):
    """异步 TCP 延迟测试"""
    info = parse_node(node)
    if not info or not info[0]: return None
    host, port = info
    try:
        start = asyncio.get_event_loop().time()
        # 尝试异步连接
        conn = asyncio.open_connection(host, port)
        await asyncio.wait_for(conn, timeout=NODE_TEST_TIMEOUT)
        latency = (asyncio.get_event_loop().time() - start) * 1000
        return (node, latency)
    except: return None

async def main():
    # 1. 搜仓库
    logging.info("正在搜索仓库...")
    repos = []
    for kw in SEARCH_KEYWORDS:
        url = f"https://api.github.com/search/repositories?q={kw}&sort=updated&per_page={MAX_REPOS_PER_KEYWORD}"
        repos.extend([r['full_name'] for r in session.get(url).json().get('items', [])])
    
    # 2. 获取文件链接
    logging.info("正在获取文件列表...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        file_urls = [url for sublist in executor.map(get_repo_files_bulk, set(repos)) for url in sublist]
    
    # 3. 提取节点 (异步)
    logging.info(f"正在处理 {len(file_urls)} 个文件...")
    async with aiohttp.ClientSession() as aio_sess:
        tasks = [fetch_and_extract(aio_sess, url) for url in file_urls]
        await asyncio.gather(*tasks)
    
    # 4. 测试延迟 (异步)
    logging.info(f"正在测试 {len(nodes_found)} 个节点的延迟...")
    async with aiohttp.ClientSession() as aio_sess:
        tasks = [check_latency(node, aio_sess) for node in nodes_found]
        results = await asyncio.gather(*tasks)
    
    valid = sorted([r for r in results if r], key=lambda x: x[1])
    
    # 5. 输出
    output = base64.b64encode("\n".join([r[0] for r in valid]).encode()).decode()
    with open(OUTPUT_FILE, 'w') as f:
        f.write(output)
    logging.info(f"任务完成，有效节点: {len(valid)}，已写入 {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
