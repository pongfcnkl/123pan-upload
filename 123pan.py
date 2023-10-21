import requests
import hashlib
import os
import sys
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def open_request(path, data, token):
    url = 'https://open-api.123pan.com' + path
    headers = {
        'Content-Type': 'application/json',
        'Platform': 'open_platform',
        'Authorization': 'Bearer ' + token
    }
    time.sleep(1)
    response = requests.post(url, data=data, headers=headers, verify=False)
    res = response.json()
    if not res.get('code') == 0:
        raise Exception(res.get('message', '网络错误'))
    return res.get('data')

def put_part(url, part_stream, part_size):
    response = requests.put(url, data=part_stream, verify=False)
    if response.status_code != 200:
        raise Exception(f'分片传输错误，错误码：{response.status_code}，错误信息：{response.text}')

def upload_file(client_id, client_secret, parent, file_path):
    token = ''
    try:
        res_data = open_request('/api/v1/access_token', {'clientID': client_id, 'clientSecret': client_secret}, token)
        token = res_data['accessToken']
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_etag = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
        res_data = open_request('/upload/v1/file/create', {
            'parentFileID': parent,
            'filename': filename,
            'etag': file_etag,
            'size': file_size
        }, token)
        if res_data['reuse']:
            print('极速上传成功')
            return
        upload_id = res_data['preuploadID']
        slice_size = res_data['sliceSize']
        res_data = open_request('/upload/v1/file/list_upload_parts', {'preuploadID': upload_id}, token)
        parts_map = {part['partNumber']: {'size': part['size'], 'etag': part['etag']} for part in res_data['parts']}
        with open(file_path, 'rb') as file:
            for i in range(0, file_size, slice_size):
                part_num = i // slice_size + 1
                temp_stream = file.read(slice_size)
                temp_size = len(temp_stream)
                if temp_size == 0:
                    break
                if parts_map.get(part_num, {}).get('size') == temp_size and parts_map.get(part_num, {}).get('etag') == hashlib.md5(temp_stream).hexdigest():
                    continue
                res_data = open_request('/upload/v1/file/get_upload_url', {'preuploadID': upload_id, 'sliceNo': part_num}, token)
                put_part(res_data['presignedURL'], temp_stream, temp_size)
        res_data = open_request('/upload/v1/file/upload_complete', {'preuploadID': upload_id}, token)
        if res_data['completed']:
            print('上传成功')
            return
        for _ in range(200):
            time.sleep(5)
            res_data = open_request('/upload/v1/file/upload_async_result', {'preuploadID': upload_id}, token)
            if res_data['completed']:
                print('上传成功')
                return
        print('上传超时')
    except Exception as e:
        print(f'上传失败：{e}')

if len(sys.argv) < 2:
    print('请提供本地文件路径作为命令行参数')
    sys.exit(1)

client_id = ''  # 用户申请到的clientID
client_secret = ''  # 用户申请到的clientSecret
parent_file_id = 0  # 上传到的父级目录id，根目录为0
local_file_path = sys.argv[1]  # 用户本地的文件绝对路径
upload_file(client_id, client_secret, parent_file_id, local_file_path)
