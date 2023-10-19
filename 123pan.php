<?php
/**
 * @throws ErrorException
 */
function open_request($path, $data, $token)
{
    $curl = curl_init('https://open-api.123pan.com' . $path);
    curl_setopt($curl, CURLOPT_POST, true);
    curl_setopt($curl, CURLOPT_POSTFIELDS, http_build_query($data));
    curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($curl, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($curl, CURLOPT_HTTPHEADER, [
        'Content-Type: application/json',
        'Platform: open_platform',
        'Authorization: Bearer ' . $token
    ]);
    $res_str = curl_exec($curl);
    curl_close($curl);
    $res = json_decode($res_str, true);
    if (!isset($res['code']) || $res['code'] != 0) {
        throw new ErrorException(isset($res['message']) ? $res['message'] : '网络错误');
    }
    return isset($res['data']) ? $res['data'] : null;
}

/**
 * @throws ErrorException
 */
function put_part($url, $part_stream, $part_size)
{
    $curl = curl_init($url);
    curl_setopt($curl, CURLOPT_PUT, true);
    curl_setopt($curl, CURLOPT_INFILE, $part_stream);
    curl_setopt($curl, CURLOPT_INFILESIZE, $part_size);
    curl_setopt($curl, CURLOPT_SSL_VERIFYPEER, false);
    $res_str = curl_exec($curl);
    $status_code = curl_getinfo($curl, CURLINFO_HTTP_CODE);
    curl_close($curl);
    if ($status_code != 200) {
        throw new ErrorException('分片传输错误，错误码：' . $status_code . '，错误信息：' . $res_str);
    }
}

function upload_file($client_id, $client_secret, $parent, $file_path)
{
    $token = '';
    try {
        $res_data = open_request('/api/v1/access_token', ['clientID' => $client_id, 'clientSecret' => $client_secret], $token);
        $token = $res_data['accessToken'];
        $filename = basename($file_path);
        $file_size = filesize($file_path);
        $file_etag = md5_file($file_path);
        $res_data = open_request('/upload/v1/file/create', [
            'parentFileID' => $parent,
            'filename' => $filename,
            'etag' => $file_etag,
            'size' => $file_size
        ], $token);
        if ($res_data['reuse']) {
            echo '极速上传成功';
            return;
        }
        $upload_id = $res_data['preuploadID'];
        $slice_size = $res_data['sliceSize'];
        $res_data = open_request('/upload/v1/file/list_upload_parts', ['preuploadID' => $upload_id], $token);
        $parts_map = [];
        foreach ($res_data['parts'] as $part) {
            $parts_map[$part['partNumber']] = ['size' => $part['size'], 'etag' => $part['etag']];
        }
        $file = fopen($file_path, 'r');
        for ($i = 0; ; $i++) {
            $part_num = $i + 1;
            $temp_stream = fopen('php://temp', 'wr');
            $temp_size = stream_copy_to_stream($file, $temp_stream, $slice_size, $i * $slice_size);
            if (!$temp_size) {
                break;
            }
            if (isset($parts_map[$part_num]) && $parts_map[$part_num]['size'] == $temp_size && $parts_map[$part_num]['etag'] == md5(stream_get_contents($temp_stream))) {
                continue;
            }
            $res_data = open_request('/upload/v1/file/get_upload_url', ['preuploadID' => $upload_id, 'sliceNo' => $part_num], $token);
            rewind($temp_stream);
            put_part($res_data['presignedURL'], $temp_stream, $temp_size);
        }
        $res_data = open_request('/upload/v1/file/upload_complete', ['preuploadID' => $upload_id], $token);
        if ($res_data['completed']) {
            echo '上传成功';
            return;
        }
        for ($j = 0; $j < 200; $j++) {
            sleep(5);
            $res_data = open_request('/upload/v1/file/upload_async_result', ['preuploadID' => $upload_id], $token);
            if ($res_data['completed']) {
                echo '上传成功';
                return;
            }
        }
        echo '上传超时';
    } catch (ErrorException $e) {
        echo '上传失败：' . $e;
    }
}

$client_id = 'myClientID'; // 用户申请到的clientID
$client_secret = 'myClientSecret'; // 用户申请到的clientSecret
$parent_file_id = 0; // 上传到的父级目录id，根目录为0
$local_file_path = 'C:\Users\admin\myFile.txt'; // 用户本地的文件绝对路径
upload_file($client_id, $client_secret, $parent_file_id, $local_file_path);
