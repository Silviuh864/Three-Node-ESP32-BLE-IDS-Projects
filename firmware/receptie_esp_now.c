#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_wifi.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "esp_now.h"
#include "driver/uart.h"
#define MAX_DEVICE_NAME_LEN 32

#define RX_BUF_SIZE (2048)
#define TX_BUF_SIZE (2048)
#define LINE_BUF_SIZE 128
const uart_port_t uart_num = UART_NUM_0;
uart_config_t uart_config = {
    .baud_rate = 460800,
    .data_bits = UART_DATA_8_BITS,
    .parity = UART_PARITY_DISABLE,
    .stop_bits = UART_STOP_BITS_1,
    .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    .source_clk = UART_SCLK_DEFAULT,
    .rx_flow_ctrl_thresh = 122,
};

typedef struct {
    uint8_t tip;
    char Nod[8];
    bool start;
} __attribute__((packed)) esp_now_start_t;

typedef struct {
    uint8_t tip;
    char Nod[8];
    bool calib;
    float rssi_1m;
} __attribute__((packed)) esp_now_calib_t;

typedef struct {
    uint8_t tip;
    char Nod[8];
    uint8_t chunk_index;
    uint8_t chunk_total;
    uint8_t count;
    struct {
        uint8_t mac[6];
        float   last_rssi_filtrat;
    } devices[10]; 
} __attribute__((packed)) esp_now_snapshot_t;

typedef struct {
    uint8_t  tip;
    char     Nod[8];
    char     device_name[MAX_DEVICE_NAME_LEN];
    uint8_t  Mac[6];
    uint8_t  addr_type;
    uint16_t mfg_id;
} __attribute__((packed)) esp_now_alerta_t;

// --- CALLBACK RECEPTIE ---

void OnDataRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
    if (len < 1) return;

    char line_buf[LINE_BUF_SIZE];
    uint8_t tip_mesaj = data[0];

    switch (tip_mesaj) {
        case 0: // Mesaj Start Calibrare
            if (len >= sizeof(esp_now_start_t)) {
                esp_now_start_t *m = (esp_now_start_t*)data;
                int written = snprintf(line_buf, sizeof(line_buf), "0|%s|STATUS:START\n", m->Nod);
                uart_write_bytes(uart_num, line_buf, written);
            }
            break;

        case 1: // Mesaj Calibrare Finalizată
            if (len >= sizeof(esp_now_calib_t)) {
                esp_now_calib_t *m = (esp_now_calib_t*)data;
                int written = snprintf(line_buf, sizeof(line_buf), "1|%s|STATUS:CALIBRAT |RSSI_1M:%.2f\n", m->Nod, m->rssi_1m);
                uart_write_bytes(uart_num, line_buf, written);
            }
            break;

        case 2: // Mesaj Snapshot (Chunk) - MULTI DEVICE
            if (len >= sizeof(esp_now_snapshot_t)) {
                esp_now_snapshot_t *m = (esp_now_snapshot_t*)data;
                // Pentru fiecare device din chunk, scoatem o linie pe serială
                for (int i = 0; i < m->count; i++) {
                    int written = snprintf(line_buf, sizeof(line_buf), 
                                   "2|%s|MAC:" MACSTR "|RSSI:%.2f\n", 
                                   m->Nod, MAC2STR(m->devices[i].mac), m->devices[i].last_rssi_filtrat);
            if (written > 0) {
                uart_write_bytes(uart_num, line_buf, written);
                }
            }
        }
            break;

        case 3: // Mesaj Alertă (Intrusion Detection)
            if (len >= sizeof(esp_now_alerta_t)) {
                esp_now_alerta_t *m = (esp_now_alerta_t*)data;
                int written = snprintf(line_buf, sizeof(line_buf), "3|%s|MAC:" MACSTR "|TYPE:%d|MFG:0x%04X|NAME:%s\n",
                       m->Nod,
                       MAC2STR(m->Mac),
                       m->addr_type,
                       m->mfg_id,
                       m->device_name);
                uart_write_bytes(uart_num, line_buf, written);
            }
            break;

        default:
            // Opțional: logare mesaje necunoscute pentru debugging RF
            break;
    }
}

// --- CONFIGURARE ȘI MAIN ---

void app_main(void) {
    
    uart_param_config(uart_num, &uart_config);
    uart_driver_install(uart_num, RX_BUF_SIZE * 2, TX_BUF_SIZE * 2, 0, NULL, 0);
    uart_set_pin(uart_num, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // 2. Configurare WiFi în mod Station (dar fără conectare la AP)
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    // 3. Initializare ESP-NOW
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(OnDataRecv));

    // Afișăm MAC-ul Master-ului (util pentru a-l seta pe Noduri)
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
   char init_buf[128];
   int init_len;
   init_len = snprintf(init_buf, sizeof(init_buf), "\n--- MASTER READY ---\n");
   uart_write_bytes(uart_num, init_buf, init_len);
   init_len = snprintf(init_buf, sizeof(init_buf), "MAC Master: " MACSTR "\n", MAC2STR(mac));
   uart_write_bytes(uart_num, init_buf, init_len);
   init_len = snprintf(init_buf, sizeof(init_buf), "--------------------\n");
   uart_write_bytes(uart_num, init_buf, init_len);
    // Loop-ul principal rămâne liber pentru alte task-uri de diagnoză
    while(1) {
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}