import requests  # 导入requests库，用于发送HTTP请求
import hashlib  # 导入hashlib库，用于计算文件的哈希值
import os  # 导入os库，用于处理文件和文件路径
import sys  # 导入sys库，用于处理命令行参数
import time  # 导入time库，用于进行时间相关的操作
import urllib3  # 导入urllib3库，用于禁用证书验证警告

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # 禁用证书验证警告

def open_request(path, data, token):
    # 发送POST请求到指定路径，使用指定数据和token进行身份验证
    url = 'https://open-api.123pan.com' + path
    headers = {
        'Content-Type': 'application/json',
        'Platform': 'open_platform',
        'Authorization': 'Bearer ' + token
    }
    response = requests.post(url, data=data, headers=headers, verify=False)  # 发送POST请求
    res = response.json()  # 解析响应数据为JSON格式
    if not res.get('code') == 0:  # 如果返回的code不为0，则抛出异常
        raise Exception(res.get('message', '网络错误'))
    return res.get('data')  # 返回响应数据中的data字段

def put_part(url, part_stream, part_size):
    # 发送PUT请求到指定URL，将分片数据上传到服务器
    response = requests.put(url, data=part_stream, verify=False)  # 发送PUT请求
    if response.status_code != 200:  # 如果返回的状态码不为200，则抛出异常
        raise Exception(f'分片传输错误，错误码：{response.status_code}，错误信息：{response.text}')

def upload_file(client_id, client_secret, parent, file_path):
    token = ''  # 初始化token为空字符串
    try:
        # 获取访问令牌
        res_data = open_request('/api/v1/access_token', {'clientID': client_id, 'clientSecret': client_secret}, token)
        token = res_data['accessToken']  # 获取访问令牌
        filename = os.path.basename(file_path)  # 获取文件名
        file_size = os.path.getsize(file_path)  # 获取文件大小
        file_etag = hashlib.md5(open(file_path, 'rb').read()).hexdigest()  # 计算文件的MD5哈希值
        # 创建文件上传任务
        res_data = open_request('/upload/v1/file/create', {
            'parentFileID': parent,
            'filename': filename,
            'etag': file_etag,
            'size': file_size
        }, token)
        if res_data['reuse']:
            print('极速上传成功')
            return
        upload_id = res_data['preuploadID']  # 获取上传任务的ID
        slice_size = res_data['sliceSize']  # 获取分片大小
        # 获取已上传的分片信息
        res_data = open_request('/upload/v1/file/list_upload_parts', {'preuploadID': upload_id}, token)
        parts_map = {part['partNumber']: {'size': part['size'], 'etag': part['etag']} for part in res_data['parts']}
        with open(file_path, 'rb') as file:
            for i in range(0, file_size, slice_size):
                part_num = i // slice_size + 1  # 计算当前分片的编号
                temp_stream = file.read(slice_size)  # 读取分片数据
                temp_size = len(temp_stream)  # 获取分片数据的大小
                if temp_size == 0:
                    break
                # 检查分片是否已上传过，如果是则跳过
                if parts_map.get(part_num, {}).get('size') == temp_size and parts_map.get(part_num, {}).get('etag') == hashlib.md5(temp_stream).hexdigest():
                    continue
                # 获取分片上传的URL，并将分片数据上传
                res_data = open_request('/upload/v1/file/get_upload_url', {'preuploadID': upload_id, 'sliceNo': part_num}, token)
                put_part(res_data['presignedURL'], temp_stream, temp_size)
        # 标记上传任务为完成状态
        res_data = open_request('/upload/v1/file/upload_complete', {'preuploadID': upload_id}, token)
        if res_data['completed']:
            print('上传成功')
            return
        # 等待上传任务完成
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
upload_file(client_id, client_secret, parent_file_id, local_file_path)  # 调用上传文件的函数并传入参数
