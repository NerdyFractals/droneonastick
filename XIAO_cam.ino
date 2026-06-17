/**
 * XIAO ESP32-S3 Sense — MJPEG WiFi Camera Stream
 * Board: Seeed Studio XIAO ESP32S3 (with camera)
 * Arduino IDE: install "esp32" board package by Espressif
 * No extra libraries needed beyond the esp32 package.
 *
 * After flashing, open Serial Monitor at 115200 baud.
 * The IP address printed there is what your Python script connects to.
 * Stream URL:  http://<IP>/stream
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// ── WiFi credentials ──────────────────────────────────────────────────────────
const char* WIFI_SSID = "YOUR_SSID";
const char* WIFI_PASS = "YOUR_PASSWORD";

// ── XIAO ESP32-S3 Sense camera pin map ────────────────────────────────────────
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13

// ── MJPEG stream boundary ─────────────────────────────────────────────────────
#define PART_BOUNDARY "frame"
static const char* STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* STREAM_PART =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;

// ── Stream handler ─────────────────────────────────────────────────────────────
static esp_err_t stream_handler(httpd_req_t* req) {
    camera_fb_t* fb = NULL;
    esp_err_t res = ESP_OK;
    char part_buf[64];

    res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
    if (res != ESP_OK) return res;

    // Disable response buffering so frames push through immediately
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) { Serial.println("Camera capture failed"); res = ESP_FAIL; break; }

        // Boundary
        res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (res != ESP_OK) { esp_camera_fb_return(fb); break; }

        // Part header with JPEG size
        size_t hlen = snprintf(part_buf, sizeof(part_buf), STREAM_PART, fb->len);
        res = httpd_resp_send_chunk(req, part_buf, hlen);
        if (res != ESP_OK) { esp_camera_fb_return(fb); break; }

        // JPEG payload
        res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);
        esp_camera_fb_return(fb);
        if (res != ESP_OK) break;
    }
    return res;
}

// ── Start HTTP server on port 80 ───────────────────────────────────────────────
void startCameraServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.max_uri_handlers = 2;

    httpd_uri_t stream_uri = {
        .uri       = "/stream",
        .method    = HTTP_GET,
        .handler   = stream_handler,
        .user_ctx  = NULL
    };

    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        Serial.println("Stream server started");
    }
}

// ── setup ──────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    // Camera config
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;
    config.pin_d0       = Y2_GPIO_NUM;
    config.pin_d1       = Y3_GPIO_NUM;
    config.pin_d2       = Y4_GPIO_NUM;
    config.pin_d3       = Y5_GPIO_NUM;
    config.pin_d4       = Y6_GPIO_NUM;
    config.pin_d5       = Y7_GPIO_NUM;
    config.pin_d6       = Y8_GPIO_NUM;
    config.pin_d7       = Y9_GPIO_NUM;
    config.pin_xclk     = XCLK_GPIO_NUM;
    config.pin_pclk     = PCLK_GPIO_NUM;
    config.pin_vsync    = VSYNC_GPIO_NUM;
    config.pin_href     = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn     = PWDN_GPIO_NUM;
    config.pin_reset    = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size   = FRAMESIZE_VGA;   // 640×480 — good for AprilTag detection
    config.jpeg_quality = 12;              // 0=best, 63=worst; 12 is a solid middle
    config.fb_count     = 2;
    config.grab_mode    = CAMERA_GRAB_LATEST;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed: 0x%x\n", err);
        while (true) delay(1000);  // halt
    }
    Serial.println("Camera ready");

    // WiFi
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.println();
    Serial.print("Connected! Stream at: http://");
    Serial.print(WiFi.localIP());
    Serial.println("/stream");

    startCameraServer();
}

// ── loop — nothing to do, server runs in background ───────────────────────────
void loop() {
    delay(10000);
}
