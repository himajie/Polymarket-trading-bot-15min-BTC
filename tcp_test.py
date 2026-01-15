import socket

def simple_tcp_server(host='0.0.0.0', port=8000):
    """简单的TCP服务器，打印客户端IP"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(5)
    
    print(f"服务器启动，监听 {host}:{port}")
    
    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"收到来自 {client_address[0]}:{client_address[1]} 的连接")
            
            # 接收数据（可选）
            try:
                data = client_socket.recv(1024)
                if data:
                    print(f"接收到的数据: {data.decode('utf-8', errors='ignore')}")
            except:
                pass
            
            # 发送简单响应
            response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nHello, your IP has been logged."
            client_socket.send(response)
            client_socket.close()
            
    except KeyboardInterrupt:
        print("\n服务器关闭")
    finally:
        server_socket.close()

if __name__ == "__main__":
    simple_tcp_server()