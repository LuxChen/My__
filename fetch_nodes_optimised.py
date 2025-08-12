import requests
import re
import base64
import json
import time
import socket
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote
import os
from dotenv import load_dotenv
from git import Repo
try:
    from git import Repo, exc
    GITPYTHON_INSTALLED = True
except ImportError:
    GITPYTHON_INSTALLED = False


# --- 配置 ---
# Load environment variables from a .env file
load_dotenv()

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 可配置参数 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
SEARCH_KEYWORDS = ["vmess", "vless", "trojan", "ss", "ssr"] # 增加关键词
MAX_REPOS_PER_KEYWORD = 5    # 每个关键词搜索多少个仓库
MAX_WORKERS = 15           # 并发下载和提取的最大线程数
MAX_NODES_PER_FILE = 100   # 单个文件提取节点上限 (适当放宽)
OUTPUT_FILE = "newlinks.txt" # 输出文件名
NODE_TEST_TIMEOUT = 3      # 节点延迟测试超时时间 (秒)

# --- GitHub API 请求头 ---
headers = {'Accept': 'application/vnd.github.v3+json'}
if GITHUB_TOKEN:
    headers['Authorization'] = f'token {GITHUB_TOKEN}'

# --- 全局变量 ---
all_collected_nodes = set() # 使用集合存储所有唯一的节点链接

def search_github_repositories(keyword, page=1):
    """使用 GitHub API 搜索仓库，支持分页"""
    logging.info(f"正在搜索关键词: '{keyword}' (第 {page} 页)")
    search_url = f"https://api.github.com/search/repositories?q={keyword}&sort=updated&order=desc&per_page=100&page={page}"
    try:
        response = requests.get(search_url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json().get('items', [])
    except requests.RequestException as e:
        logging.error(f"搜索关键词 '{keyword}' 时发生网络错误: {e}")
        return []
    except Exception as e:
        logging.error(f"搜索关键词 '{keyword}' 时发生未知错误: {e}")
        return []

def get_repo_files_recursive(repo_name, path=''):
    """递归获取仓库中所有文件的下载链接"""
    contents_url = f"https://api.github.com/repos/{repo_name}/contents/{path}"
    try:
        logging.info(f"正在获取仓库 {repo_name} 的内容: {path}")
        response = requests.get(contents_url, headers=headers, timeout=10)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        contents = response.json()
        
        file_urls = []
        if not isinstance(contents, list):
            return []

        for item in contents:
            # 筛选可能包含节点信息的文件
            file_name_lower = item['name'].lower()
            if item['type'] == 'file':
                if any(ext in file_name_lower for ext in ['.txt', '.md', '.json']) or \
                   any(kw in file_name_lower for kw in ['sub', 'node', 'v2ray', 'clash']):
                    if item.get('download_url'):
                        file_urls.append(item['download_url'])
            elif item['type'] == 'dir':
                pass
                # 递归进入子目录
                # time.sleep(0.1) # 避免过于频繁的 API 请求
                # file_urls.extend(get_repo_files_recursive(repo_name, item['path']))
        logging.info(f"仓库 {repo_name} 的路径 '{path}' 中找到 {len(file_urls)} 个文件链接")
        return file_urls
    except requests.RequestException:
        return [] # 忽略网络错误
    except Exception:
        return [] # 忽略其他错误

def extract_nodes_from_content(content):
    """从文本内容中提取节点链接"""
    nodes = set()
    protocols = ['vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://']
    
    # 1. 直接匹配协议链接
    for proto in protocols:
        found = re.findall(rf"{proto}[^\s\'\"<>\[\]\(\{{}}]+", content)
        nodes.update(found)

    # 2. 尝试解码 Base64 编码的订阅内容
    try:
        # 假设整个文件内容可能是 Base64 编码的订阅
        if len(content) > 50 and not any(p in content for p in protocols):
            decoded_content = base64.b64decode(content).decode('utf-8', errors='ignore')
            for proto in protocols:
                found_in_b64 = re.findall(rf"{proto}[^\s\'\"<>\[\]\(\{{}}]+", decoded_content)
                nodes.update(found_in_b64)
    except Exception:
        pass # 忽略解码错误

    return nodes

def process_file_url(file_url):
    """下载单个文件并提取节点"""
    try:
        response = requests.get(file_url, headers=headers, timeout=15)
        response.raise_for_status()
        content = response.text
        
        nodes_in_file = extract_nodes_from_content(content)
        
        if len(nodes_in_file) > MAX_NODES_PER_FILE:
            logging.warning(f"忽略文件 (节点过多 > {MAX_NODES_PER_FILE}): {file_url}")
            return set()
            
        if nodes_in_file:
            logging.info(f"从 {urlparse(file_url).path.split('/')[-1]} 提取到 {len(nodes_in_file)} 个节点")
        return nodes_in_file
    except requests.RequestException:
        return set()
    except Exception:
        return set()

def parse_node_link(node_link):
    """解析节点链接，返回 (地址, 端口) 或 None"""
    try:
        if node_link.startswith('vmess://'):
            decoded_part = base64.b64decode(node_link[8:]).decode('utf-8')
            node_data = json.loads(decoded_part)
            return node_data.get('add'), int(node_data.get('port', 0))
        elif node_link.startswith(('vless://', 'trojan://')):
            parsed_url = urlparse(node_link)
            return parsed_url.hostname, parsed_url.port or 443
        elif node_link.startswith('ss://'):
            # ss://method:pass@host:port#remark -> b64(method:pass)@host:port
            uri_part = node_link.split('@')[1]
            host, port_str = uri_part.split('#')[0].rsplit(':', 1)
            return host, int(port_str)
        elif node_link.startswith('ssr://'):
            # ssr://host:port:proto:method:obfs:b64(password)/?params
            decoded_link = base64.b64decode(node_link[6:] + '==').decode('utf-8')
            parts = decoded_link.split(':')
            if len(parts) >= 6:
                return parts[0], int(parts[1])
    except Exception:
        return None
    return None

def test_node_latency(node_link, timeout=NODE_TEST_TIMEOUT):
    """测试单个节点的 TCP 连接延迟"""
    parsed_info = parse_node_link(node_link)
    if not parsed_info or not parsed_info[0] or not parsed_info[1]:
        return node_link, float('inf')

    address, port = parsed_info
    try:
        start_time = time.time()
        with socket.create_connection((address, port), timeout=timeout):
            latency = (time.time() - start_time) * 1000
            return node_link, latency
    except (socket.timeout, ConnectionRefusedError, OSError):
        return node_link, float('inf')
    except Exception:
        return node_link, float('inf')

def search_phase():
    """阶段一：搜索 GitHub 仓库并获取文件链接"""
    logging.info("--- 阶段 1/4: 搜索 GitHub 仓库 ---")
    repos_to_check = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_keyword = {executor.submit(search_github_repositories, kw): kw for kw in SEARCH_KEYWORDS}
        for future in as_completed(future_to_keyword):
            try:
                repos = future.result()
                if repos:
                    repos_to_check.extend(repos[:MAX_REPOS_PER_KEYWORD])
            except Exception as e:
                logging.error(f"获取仓库列表时出错: {e}")

    unique_repos = {repo['full_name']: repo for repo in repos_to_check if 'full_name' in repo}
    logging.info(f"找到 {len(unique_repos)} 个不重复的仓库。")
    
    all_file_urls = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_repo = {executor.submit(get_repo_files_recursive, name): name for name in unique_repos.keys()}
        for future in as_completed(future_to_repo):
            try:
                all_file_urls.extend(future.result())
            except Exception as e:
                logging.error(f"处理仓库 {future_to_repo[future]} 时出错: {e}")

    unique_file_urls = list(set(all_file_urls))
    logging.info(f"找到 {len(unique_file_urls)} 个唯一的文件链接待处理。")
    return unique_file_urls

def extraction_phase(file_urls):
    """阶段二：并发处理文件，提取节点"""
    logging.info("\n--- 阶段 2/4: 并发下载文件并提取节点 ---")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(process_file_url, url): url for url in file_urls}
        
        for i, future in enumerate(as_completed(future_to_url), 1):
            try:
                nodes_from_file = future.result()
                if nodes_from_file:
                    count_before = len(all_collected_nodes)
                    all_collected_nodes.update(nodes_from_file)
                    added_count = len(all_collected_nodes) - count_before
                    if added_count > 0:
                        logging.info(f"新增 {added_count} 个唯一节点 (总计: {len(all_collected_nodes)})")
                
                print(f"\r处理进度: {i}/{len(file_urls)} | 当前收集: {len(all_collected_nodes)} 个", end="")
            except Exception as e:
                logging.error(f"处理文件时产生异常: {e}")
    print() # 换行
    logging.info("文件处理完成。")

def testing_phase():
    """阶段三：测试节点延迟并排序"""
    logging.info(f"\n--- 阶段 3/4: 测试 {len(all_collected_nodes)} 个节点的延迟 ---")
    valid_nodes = []
    if not all_collected_nodes:
        return valid_nodes

    with ThreadPoolExecutor(max_workers=MAX_WORKERS * 2) as executor:
        future_to_node = {executor.submit(test_node_latency, node): node for node in all_collected_nodes}
        
        total_nodes = len(all_collected_nodes)
        for i, future in enumerate(as_completed(future_to_node), 1):
            try:
                node, latency = future.result()
                if latency != float('inf'):
                    valid_nodes.append((node, latency))
                    print(f"\r有效节点: {len(valid_nodes)} | 测试进度: {i}/{total_nodes} | 最新延迟: {latency:.2f} ms", end="")
                else:
                    print(f"\r有效节点: {len(valid_nodes)} | 测试进度: {i}/{total_nodes} | (节点无效或超时)", end="")
            except Exception as e:
                logging.error(f"测试节点时出错: {e}")

    valid_nodes.sort(key=lambda x: x[1])
    print() # 换行
    logging.info("节点延迟测试完成。")
    return valid_nodes

def output_phase(valid_nodes):
    """阶段四：输出结果到文件"""
    logging.info(f"\n--- 阶段 4/4: 输出结果 ---")
    logging.info(f"总共收集到 {len(all_collected_nodes)} 个唯一节点，其中 {len(valid_nodes)} 个有效。")

    if not valid_nodes:
        logging.warning("未找到任何有效的节点。")
        return

    logging.info(f"将 {len(valid_nodes)} 个有效节点按延迟排序后写入文件: {OUTPUT_FILE}")
    try:
        # 将所有节点链接合并为一个字符串
        output_content = "\n".join([node for node, latency in valid_nodes])
        # 使用 Base64 编码
        encoded_content = base64.b64encode(output_content.encode('utf-8')).decode('utf-8')
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(encoded_content)
        logging.info(f"成功将 {len(valid_nodes)} 个有效节点（Base64编码）写入 {OUTPUT_FILE}")
    except IOError as e:
        logging.error(f"写入文件时出错: {e}")
        
def commit_and_push_results():
    """使用 GitPython 将结果提交并推送到GitHub (Commit and push results to GitHub using GitPython)"""
    if not GITPYTHON_INSTALLED:
        logging.warning("GitPython 未安装，跳过自动提交。请运行 'pip install GitPython'。")
        return

    if not os.path.exists(OUTPUT_FILE):
        logging.warning(f"输出文件 {OUTPUT_FILE} 不存在，跳过提交。")
        return
    
    try:
        logging.info("正在将结果提交到GitHub...")
        repo = Repo(os.getcwd())
        if not repo.is_dirty(path=OUTPUT_FILE) and OUTPUT_FILE not in repo.untracked_files:
            logging.info("文件没有变化，无需提交。")
            return

        repo.git.add(OUTPUT_FILE)
        commit_message = f"Update nodes on {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
        repo.git.commit('-m', commit_message)
        
        logging.info("正在推送到远程仓库...")
        origin = repo.remote(name='origin')
        origin.push()
        logging.info("成功提交并推送到GitHub。")
    except exc.InvalidGitRepositoryError:
        logging.error("错误：脚本不在一个Git仓库中运行。")
    except Exception as e:
        logging.error(f"发生未知的Git操作错误: {e}")        

if __name__ == "__main__":
    start_time = time.time()
    
    # 执行各个阶段
    file_urls_to_process = search_phase()
    extraction_phase(file_urls_to_process)
    tested_nodes = testing_phase()
    output_phase(tested_nodes)
    commit_and_push_results()
    end_time = time.time()
    logging.info(f"\n--- 任务完成 (总耗时: {end_time - start_time:.2f} 秒) ---")