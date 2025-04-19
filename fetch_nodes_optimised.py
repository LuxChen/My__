import requests
import re
import base64
import json
import time # 保留 time 用于计算总耗时
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import os
from dotenv import load_dotenv
# --- 配置 ---
# 从本地环境变量中获取 GitHub Token
# Load environment variables from a .env file
load_dotenv()
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
SEARCH_KEYWORDS = [
    "vmess"
]
MAX_REPOS_PER_KEYWORD = 20   # 每个关键词搜索多少个仓库
MAX_WORKERS = 10           # 并发下载和提取的最大线程数
MAX_NODES_PER_FILE = 50   # 单个文件提取节点上限
OUTPUT_FILE = "newlinks.txt" # 输出文件名

# --- GitHub API 请求头 ---
headers = {'Accept': 'application/vnd.github.v3+json'}
if GITHUB_TOKEN:
    headers['Authorization'] = f'token {GITHUB_TOKEN}'

# --- 全局变量 ---
all_collected_nodes = set() # 使用集合存储所有唯一的节点链接

def search_github_repositories(keyword):
    """使用 GitHub API 搜索仓库"""
    print(f"[*] 正在搜索关键词: {keyword}")

    search_url = f"https://api.github.com/search/repositories?q={keyword}&sort=updated&order=desc&per_page=10"
    try:
        response = requests.get(search_url, headers=headers, timeout=15)
        response.raise_for_status()
        items = response.json().get('items', [])
        if not items:
            print(f"[!] 未找到与 '{keyword}' 相关的仓库。")
            return []
        yield from items  # 使用生成器逐个返回结果
    except Exception as e:
        print(f"[!] 搜索时发生错误: {e}")
        return []
def get_repo_content_urls(repo_info):
    """获取仓库中可能包含节点信息的文件 URL"""
    repo_name = repo_info.get('full_name')
    if not repo_name: return []
    # print(f"[*] 正在检查仓库: {repo_name}") # 精简打印
    contents_url = repo_info.get('contents_url', '').replace('{+path}', '')
    files_to_check = []
    try:
        response = requests.get(contents_url, headers=headers, timeout=10)
        response.raise_for_status()
        contents = response.json()
        if isinstance(contents, list):
            for item in contents:
                file_name = item['name'].lower()
                if item['type'] == 'file' and '自建' not in file_name and '一键' not in file_name and (
                    file_name.endswith(('.txt', '.md')) or
                    'sub' in item['name'].lower() or 'node' in item['name'].lower() or
                    'v2ray' in item['name'].lower() or 'clash' in item['name'].lower()
                ):
                    if item.get('download_url'):
                         files_to_check.append(item['download_url'])
    except Exception:
        pass # 忽略获取内容失败的仓库
    return files_to_check

def extract_nodes_from_file(file_url):
    """下载文件内容并提取节点链接，单个文件超过阈值则忽略"""
    nodes_in_file = set()
    try:
        response = requests.get(file_url, headers=headers, timeout=15)
        response.raise_for_status()
        content = response.text

        # 提取节点逻辑 (与之前类似)
        protocols = ['vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://']
        for proto in protocols:
            found = re.findall(rf"{proto}[^\s\'\"<>\[\]\(\{{}}]+", content)
            nodes_in_file.update(found)

        # 简化 Base64 处理 (仅文本块)
        potential_base64_blocks = re.findall(r'\b[A-Za-z0-9+/]{20,}={0,2}\b', content)
        for b64_block in potential_base64_blocks:
             try:
                cleaned_b64 = "".join(b64_block.split())
                missing_padding = len(cleaned_b64) % 4
                if missing_padding: cleaned_b64 += '=' * (4 - missing_padding)
                decoded_content = base64.b64decode(cleaned_b64).decode('utf-8', errors='ignore')
                for proto in protocols:
                    found_in_b64 = re.findall(rf"{proto}[^\s\'\"<>\[\]\(\{{}}]+", decoded_content)
                    nodes_in_file.update(found_in_b64)
             except Exception:
                 pass # 忽略解码错误

        # 检查文件节点数是否超限
        if len(nodes_in_file) > MAX_NODES_PER_FILE:
            print(f"    [!] 忽略文件 (节点过多 > {MAX_NODES_PER_FILE}): {urlparse(file_url).path.split('/')[-1]} (找到 {len(nodes_in_file)} 个)")
            return set() # 返回空集合

        # 如果数量在限制内，返回找到的节点
        if nodes_in_file:
             print(f"    [*] 从 {urlparse(file_url).path.split('/')[-1]} 提取到 {len(nodes_in_file)} 个节点")
        return nodes_in_file

    except requests.exceptions.RequestException:
        # print(f"    [!] 下载文件失败: {file_url}")
        return set()
    except Exception as e:
        # print(f"    [!] 处理文件时出错: {file_url} ({e})")
        return set()


# --- 主逻辑 ---
if __name__ == "__main__":
    print(f"--- 开始收集 GitHub 上的节点链接 (每个文件最多 {MAX_NODES_PER_FILE} 个) ---")
    start_time_main = time.time()

    # 1. 搜索 GitHub 仓库并获取文件链接
    print("[阶段 1/2] 搜索 GitHub 仓库并获取文件链接...")
    # (这部分逻辑不变)
    repos_to_check = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_keyword = {executor.submit(search_github_repositories, kw): kw for kw in SEARCH_KEYWORDS}
        for future in as_completed(future_to_keyword):
            try: 
                repos_to_check.extend(future.result())
            except Exception: pass
    unique_repos = {repo['full_name']: repo for repo in repos_to_check if 'full_name' in repo}
    repos_to_check = list(unique_repos.values())

    all_file_urls = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_repo = {executor.submit(get_repo_content_urls, repo): repo for repo in repos_to_check}
        for future in as_completed(future_to_repo):
             try: all_file_urls.extend(future.result())
             except Exception: pass
    unique_file_urls = list(set(all_file_urls))
    print(unique_file_urls) # 打印所有文件链接
    print(f"[*] 找到 {len(unique_file_urls)} 个唯一的文件链接待处理。")


    # 2. 并发处理文件：下载并提取节点
    print("\n[阶段 2/2] 并发下载文件并提取节点链接...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(extract_nodes_from_file, url): url for url in unique_file_urls}
        processed_count = 0
        total_files = len(unique_file_urls)
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                # nodes_from_file 是一个集合 (可能为空)
                nodes_from_file = future.result()
                print(f"\n[*] 处理文件: {urlparse(url).path.split('/')[-1]}")
                if nodes_from_file:
                    count_before = len(all_collected_nodes)
                    all_collected_nodes.update(nodes_from_file) # 添加到主集合，自动去重
                    added_count = len(all_collected_nodes) - count_before
                    if added_count > 0: # 只在确实有新节点时打印
                        print(f"    [+] 新增 {added_count} 个唯一节点 (总计: {len(all_collected_nodes)})")
                processed_count += 1
                # 打印进度
                print(f"\r    处理进度: {processed_count}/{total_files} (当前收集: {len(all_collected_nodes)} 个唯一节点)", end="")

            except Exception as exc:
                processed_count += 1
                print(f"\n[!] 处理文件 URL '{url}' 时产生异常: {exc}")
                print(f"\r    处理进度: {processed_count}/{total_files} (当前收集: {len(all_collected_nodes)} 个唯一节点)", end="")

    print("\n[*] 文件处理完成.")
    end_time_main = time.time()
    print(f"--- 收集结束 (耗时: {end_time_main - start_time_main:.2f} 秒) ---")

    # 3. 输出结果
    print(f"[*] 总共收集到 {len(all_collected_nodes)} 个唯一的节点链接。")

    if not all_collected_nodes:
        print("[!] 未找到任何节点信息。")
        exit()

    print(f"\n[*] 将结果写入文件: {OUTPUT_FILE}")
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            # 将集合转换为列表，然后写入，可以保证某种顺序（但不一定是特定顺序）
            nodes_list = list(all_collected_nodes)
            for node_link in nodes_list:
                f.write(node_link + '\n')
        print(f"[*] 成功将 {len(all_collected_nodes)} 个节点写入 {OUTPUT_FILE}")
    except IOError as e:
        print(f"[!] 写入文件时出错: {e}")

    print("\n--- 任务完成 ---")
