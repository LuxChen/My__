package main

import (
	"context"
	"encoding/base64"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"

	"nhooyr.io/websocket"
)

func fetchUrl(url string, ch chan string) (string, error) {
	log.Print(urls[url])
	resp, err := http.Get(url)
	if err != nil {
		ch <- "fail"
		return "", err
	}

	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		ch <- "fail"
		return "", err
	}
	return_string, err := base64.StdEncoding.DecodeString(string(body))
	if err == nil {
		ch <- string(return_string)
		return string(return_string), nil
	}
	log.Print("here end_______")
	ch <- "finish"
	return "", nil
}

var urls = map[string]string{
	"https://raw.fastgit.org/freefq/free/master/v2":                                      "raw",
	"https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.config.txt":       "raw",
	"https://github.com/mianfeifq/share":                                                 "code",
	"https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity": "raw",
}

func main() {
	// ch := make(chan string)
	// for url := range urls {
	// 	go fetchUrl(fmt.Sprintf("%v", url), ch)
	// }
	// // log.Print(err)
	// // log.Print(data_str)
	// allFinish := len(urls)
	// finished := 0
	// nodes := ""
	// for {
	// 	time.Sleep(time.Millisecond * 1e2)
	// 	if allFinish == finished {
	// 		print("finished")
	// 		break
	// 	}
	// 	nam := <-ch
	// 	print(nam)
	// 	if nam != "fail" {
	// 		nodes = nodes + nam
	// 	}
	// 	finished++
	// }
	// // Split the string.
	// wfile, _ := os.OpenFile("my_file.txt", os.O_CREATE|os.O_TRUNC, 0644)
	// slices := strings.Split(nodes, "\n")
	// t := time.After(time.Second * 5)
	// // Print the slices.
	// for _, slice := range slices {
	// 	p_v := strings.Split(slice, "://")
	// 	if len(p_v) < 2 {
	// 		continue
	// 	}
	// 	decodedBytes, _ := base64.StdEncoding.DecodeString(p_v[1])
	// 	switch p_v[0] {

	// 	case "vmess":
	// 		{

	// 			// Unmarshal the string.
	// 			var data map[string]interface{}
	// 			err := json.Unmarshal([]byte(string(decodedBytes)), &data)
	// 			if err != nil {
	// 				fmt.Println(err)
	// 				return
	// 			}

	// 			// Print the data.
	// 			address := data["host"]
	// 			port := fmt.Sprintf("%v", data["port"])
	// 			if data["path"] == nil || data["path"] == "" {
	// 				data["path"] = "/"
	// 			}
	// 			path := data["path"]
	// 			go testConn(slice, address, port, path, *wfile)
	// 		}
	// 		// case "ss":
	// 		// 	{

	// 		// 		server := strings.Split(strings.Split(p_v[1], "@")[1], "#")[0]
	// 		// 		p_g := strings.Split(string(decodedBytes), ":")
	// 		// 		c, _ := shadowsocks.NewCipher(p_g[0], p_g[1])
	// 		// 		ss, err := shadowsocks.Dial(server, server, c)
	// 		// 		if err == nil {
	// 		// 			_, err := ss.Write([]byte("GET / HTTP/1.1\r\nHost: www.google.com\r\n\r\n"))
	// 		// 			if err != nil {
	// 		// 				log.Print(err)
	// 		// 			}
	// 		// 			log.Print(slice)
	// 		// 		}
	// 		// 		log.Print(err)

	// 		// 	}

	// 	}
	// }
	// <-t
	cmd := exec.Command("git", "add", "my_file.txt")
	stdout, err := cmd.Output()

	if err != nil {
		fmt.Println(err.Error())
		return
	}

	fmt.Print(string(stdout))
	cmd = exec.Command("git", "commit", "-m", "update")
	stdout, err = cmd.Output()

	if err != nil {
		fmt.Println(err.Error())
		return
	}

	fmt.Print(string(stdout))
	cmd = exec.Command("git", "push")
	stdout, err = cmd.Output()

	if err != nil {
		fmt.Println(err.Error())
		return
	}

	fmt.Print(string(stdout))
	// Create a WebSocket connection.

}

func testConn(origin string, address, port, path interface{}, wfile os.File) {
	var (
		ctx    context.Context
		cancel context.CancelFunc
	)
	timeout, err := time.ParseDuration("3s")
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

	_, msg, err := ws.Read(ctx)
	log.Print("read", err)
	_, err = wfile.WriteString(origin + "\n")
	if err != nil && strings.Contains(err.Error(), "context deadline exceeded") {
		log.Print("here", msg, err)
	}
	if err == nil {
		log.Print("there", msg, err)
	}
}
