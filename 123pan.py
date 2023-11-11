import requests
from requests.adapters import HTTPAdapter
import hashlib
import os
import sys
import time
import urllib3
import logging

session = requests.Session()
session.mount('https://', HTTPAdapter(pool_connections=5, pool_maxsize=5))
# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def calculate_md5(file_path, chunk_size=8192):
    md5_hash = hashlib.md5()

    with open(file_path, 'rb') as file:
        while chunk := file.read(chunk_size):
            md5_hash.update(chunk)

    return md5_hash.hexdigest()
    
def open_request(path, data, token):
    url = 'https://open-api.123pan.com' + path
    headers = {
        'Content-Type': 'application/json',
        'Platform': 'open_platform',
        'Authorization': 'Bearer ' + token
    }
    time.sleep(1)
    response = session.post(url, data=data, headers=headers, verify=False)
    res = response.json()
    if not res.get('code') == 0:
        raise Exception(res.get('message', '网络错误'))
    return res.get('data')

def put_part_with_retry(url, part_stream, part_size, max_retries=199990):
    for attempt in range(max_retries):
        try:
            response = session.put(url, data=part_stream, verify=False)
            if response.status_code == 200:
                return
            else:
                raise Exception(f'分片传输错误，错误码：{response.status_code}，错误信息：{response.text}')
        except Exception as e:
            logging.error(f'分片上传失败: {e}')
            if attempt < max_retries - 1:
                logging.info(f'重试中... (尝试 {attempt + 2}/{max_retries})')
                time.sleep(1)
            else:
                logging.error('分片上传达到最大重试次数，无法继续.')

def upload_file_with_retry(client_id, client_secret, parent, file_path, max_retries=999999):
    for attempt in range(max_retries):
        try:
            token = ''
            
            # Get access token
            res_data = open_request('/api/v1/access_token', {'clientID': client_id, 'clientSecret': client_secret}, token)
            token = res_data['accessToken']
            
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_etag = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
            
            # Create file
            res_data = open_request('/upload/v1/file/create', {
                'parentFileID': parent,
                'filename': filename,
                'etag': file_etag,
                'size': file_size
            }, token)

            if res_data['reuse']:
                logging.info('极速上传成功')
                return
            
            upload_id = res_data['preuploadID']
            slice_size = res_data['sliceSize']
            
            # List upload parts
            res_data = open_request('/upload/v1/file/list_upload_parts', {'preuploadID': upload_id}, token)
            parts_map = {part['partNumber']: {'size': part['size'], 'etag': part['etag']} for part in res_data['parts']}
            
            with open(file_path, 'rb') as file:
                progress = 0
                
                for i in range(0, file_size, slice_size):
                    part_num = i // slice_size + 1
                    temp_stream = file.read(slice_size)
                    temp_size = len(temp_stream)
                    
                    if temp_size == 0:
                        break
                    
                    if parts_map.get(part_num, {}).get('size') == temp_size and parts_map.get(part_num, {}).get('etag') == hashlib.md5(temp_stream).hexdigest():
                        progress += temp_size
                        continue
                    
                    # Get upload URL
                    res_data = open_request('/upload/v1/file/get_upload_url', {'preuploadID': upload_id, 'sliceNo': part_num}, token)
                    
                    try:
                        put_part_with_retry(res_data['presignedURL'], temp_stream, temp_size)
                        progress += temp_size
                        logging.info(f'分片上传成功, Part {part_num}')
                        
                        # Calculate upload progress
                        percent_done = (progress / file_size) * 100
                        logging.info(f'上传进度: {percent_done:.2f}%')
                    
                    except Exception as e:
                        logging.error(f'分片上传失败: {e}')
                        logging.info('继续重试...')
                        time.sleep(1)
                
                # Upload complete
                res_data = open_request('/upload/v1/file/upload_complete', {'preuploadID': upload_id}, token)
                
                if res_data['completed']:
                    logging.info(f'上传成功, 文件名: {filename}')
                    return
                
                for _ in range(200):
                    time.sleep(1)
                    res_data = open_request('/upload/v1/file/upload_async_result', {'preuploadID': upload_id}, token)
                    
                    if res_data['completed']:
                        logging.info(f'上传成功, 文件名: {filename}')
                        return
                
                logging.error('上传超时')
        
        except Exception as e:
            logging.error(f'上传失败，错误信息: {e}')
            if attempt < max_retries - 1:
                logging.info(f'重试中... (尝试 {attempt + 2}/{max_retries})')
                time.sleep(5)
            else:
                logging.error('文件上传达到最大重试次数，无法继续.')
                sys.exit(1)

if len(sys.argv) < 2:
    logging.error('请提供本地文件路径作为命令行参数')
    sys.exit(1)

client_id = ''  # 用户申请到的clientID
client_secret = ''  # 用户申请到的clientSecret
parent_file_id = 0  # 上传到的父级目录id，根目录为0
local_file_path = sys.argv[1]  # 用户本地的文件绝对路径
file_etag = calculate_md5(local_file_path)
upload_file_with_retry(client_id, client_secret, parent_file_id, local_file_path)
