package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"nhooyr.io/websocket"
)

func main() {
	// Get the file name.
	filename := "newlinks.txt"
	wfile, err := os.OpenFile("my_file.txt", os.O_CREATE, 0644)
	if err != nil {
		fmt.Println(err)
		return
	}

	// Close the w.
	defer wfile.Close()
	// Open the file.
	file, err := os.Open(filename)
	if err != nil {
		fmt.Println(err)
		return
	}

	// Read the file.
	data := make([]byte, 1024)
	file_data := ""
	for {
		n, err := file.Read(data)
		if err != nil {
			break
		}

		// Close the file.

		// Print the file contents.
		file_data += string(data[:n])
	}
	file.Close()
	// Split the string.
	slices := strings.Split(file_data, "\n")
	t := time.After(time.Second * 5)
	// Print the slices.
	for _, slice := range slices {
		p_v := strings.Split(slice, "://")
		log.Print(p_v)
		decodedBytes, _ := base64.StdEncoding.DecodeString(p_v[1])
		switch p_v[0] {

		case "vmess":
			{

				// Unmarshal the string.
				var data map[string]interface{}
				err := json.Unmarshal([]byte(string(decodedBytes)), &data)
				if err != nil {
					fmt.Println(err)
					return
				}

				// Print the data.
				address := data["host"]
				port := fmt.Sprintf("%v", data["port"])
				if data["path"] == nil || data["path"] == "" {
					data["path"] = "/"
				}
				path := data["path"]
				go testConn(slice, address, port, path, *wfile)
			}
			// case "ss":
			// 	{

			// 		server := strings.Split(strings.Split(p_v[1], "@")[1], "#")[0]
			// 		p_g := strings.Split(string(decodedBytes), ":")
			// 		c, _ := shadowsocks.NewCipher(p_g[0], p_g[1])
			// 		ss, err := shadowsocks.Dial(server, server, c)
			// 		if err == nil {
			// 			_, err := ss.Write([]byte("GET / HTTP/1.1\r\nHost: www.google.com\r\n\r\n"))
			// 			if err != nil {
			// 				log.Print(err)
			// 			}
			// 			log.Print(slice)
			// 		}
			// 		log.Print(err)

			// 	}

		}
	}
	<-t
	// Create a WebSocket connection.

}

func testConn(origin string, address, port, path interface{}, wfile os.File) {
	var (
		ctx    context.Context
		cancel context.CancelFunc
	)
	timeout, err := time.ParseDuration("1.5s")
	if err == nil {
		// The request has a timeout, so create a context that is
		// canceled automatically when the timeout expires.
		ctx, cancel = context.WithTimeout(context.Background(), timeout)
	} else {
		ctx, cancel = context.WithCancel(context.Background())
	}
	defer cancel() // Cancel ctx as soon as handleSearch returns.
	url_str := fmt.Sprintf("ws://%v:%v%v", address, port, path)
	ws, _, err := websocket.Dial(ctx, url_str, nil)
	if err != nil {
		log.Println(err)
		if strings.Contains(err.Error(), "context deadline exceeded") {
			return
		}
		// Write the string "Hello, world!" to the file.
		// _, err = wfile.WriteString(origin)
		// if err != nil {
		// 	log.Print(err)
		// 	return
		// }
		return
	}
	// Send an HTTP request.
	err = ws.Write(ctx, websocket.MessageBinary, []byte("GET / HTTP/1.1\r\nHost: www.google.com\r\n\r\n"))
	if err != nil {
		log.Print(err)
	}
	// Write the string "Hello, world!" to the file.
	_, err = wfile.WriteString(origin)
	if err != nil {
		log.Print(err)
		return
	}
}
