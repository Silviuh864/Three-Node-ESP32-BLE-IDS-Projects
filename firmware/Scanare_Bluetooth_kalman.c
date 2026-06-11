#include <stdio.h>
#include <string.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "esp_bt.h"
#include "esp_gap_ble_api.h"
#include "esp_bt_main.h"
#include "esp_bt_device.h"
#include "esp_wifi.h"
#include "esp_mac.h"
#include "esp_now.h"
#include "esp_timer.h"

static const char *TARGET_DEVICE_NAME  = "A53 al utilizatorului Deus";
uint8_t broadcastAddress[]             = {0x3C, 0x61, 0x05, 0x64, 0xFA, 0x0C};

#define NOD_ID                  "NOD:3"
#define MAX_DEVICES             100
#define MAX_DEVICES_PER_PACKET  10
#define RSSI_THRESHOLD          -75
#define PROCESS_NOISE           0.001f
#define CALIBRATION_SAMPLES     100
#define ALERT_TIMEOUT_MS        5000
#define SNAPSHOT_INTERVAL_MS    250
#define CHUNK_DELAY_MS          20
#define MAX_DEVICE_NAME_LEN 32
#define HEARTBEAT_INTERVAL_US   5000000ULL

typedef struct {
    float Q;
    float R;
    float x_est_last;
    float P_last;
} KalmanFilter;

typedef struct {
    uint8_t      mac[6];
    bool         activ;
    uint64_t     last_seen;
    KalmanFilter kf;
    bool         kf_initialized;
    float       last_rssi_filtrat;
    float       last_sent_rssi;
    uint64_t    last_sent_ts;
    bool         has_name;
} DeviceState;


typedef struct {
    uint8_t tip;
    char    Nod[8];
    bool    start;
} __attribute__((packed)) esp_now_start_t;

typedef struct {
    uint8_t tip;
    char    Nod[8];
    bool    calib;
    float  rssi_1m;
} __attribute__((packed)) esp_now_calib_t;

typedef struct {
    uint8_t tip;
    char    Nod[8];
    uint8_t chunk_index;
    uint8_t chunk_total;
    uint8_t count;
    struct {
        uint8_t mac[6];
        float   last_rssi_filtrat;
    } devices[MAX_DEVICES_PER_PACKET];
} __attribute__((packed)) esp_now_snapshot_t;
typedef struct {
    uint8_t  tip;
    char     Nod[8];
    char     device_name[MAX_DEVICE_NAME_LEN];
    uint8_t  Mac[6];
    uint8_t  addr_type;
    uint16_t mfg_id;
} __attribute__((packed)) esp_now_alerta_t;
esp_now_peer_info_t peerInfo;
DeviceState         devices[MAX_DEVICES];
esp_timer_handle_t  snap_timer;
bool  is_calibrated      = false;
bool  mesaj_sent         = false;
float dynamic_rssi_1m    = -59.0f;
float measurement_noise_R = 5.0f;
float calibration_sum    = 0.0f;
float calibration_sq_sum = 0.0f;
int   calibration_count  = 0;

static esp_ble_scan_params_t ble_scan_params = {
    .scan_type          = BLE_SCAN_TYPE_PASSIVE,
    .own_addr_type      = BLE_ADDR_TYPE_PUBLIC,
    .scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ALL,
    .scan_interval      = 0x50,
    .scan_window        = 0x50,
    .scan_duplicate     = BLE_SCAN_DUPLICATE_DISABLE
};
void kalman_init(KalmanFilter *k, float process_noise, float meas_noise, float initial_val) {
    k->Q          = process_noise;
    k->R          = meas_noise;
    k->x_est_last = initial_val;
    k->P_last     = 1.0f;
}

float kalman_update(KalmanFilter *k, float raw_val) {
    float P_temp = k->P_last + k->Q;
    float K      = P_temp / (P_temp + k->R);
    float x_est  = k->x_est_last + K * (raw_val - k->x_est_last);
    k->P_last     = (1.0f - K) * P_temp;
    k->x_est_last = x_est;
    return x_est;
}

int gaseste_device(uint8_t *mac) {
    for (int i = 0; i < MAX_DEVICES; i++)
        if (devices[i].activ && memcmp(devices[i].mac, mac, 6) == 0)
            return i;
    return -1;
}

/* Returns a free slot index, or evicts the least-recently-seen device
 * if the table is full. Never returns -1, so callers don't need to
 * guard against it anymore. */
int gaseste_loc_liber() {
    int      lru_idx = 0;
    uint64_t oldest  = UINT64_MAX;

    for (int i = 0; i < MAX_DEVICES; i++) {
        if (!devices[i].activ)
            return i;                          /* free slot found */
        if (devices[i].last_seen < oldest) {
            oldest  = devices[i].last_seen;
            lru_idx = i;
        }
    }

    /* Table full — evict the oldest device */
    printf("WARN: lista plina, evict LRU [%d]: " MACSTR "\n",
           lru_idx, MAC2STR(devices[lru_idx].mac));
    devices[lru_idx].activ          = false;
    devices[lru_idx].kf_initialized = false;
    devices[lru_idx].has_name       = false;
    memset(devices[lru_idx].mac, 0, 6);
    return lru_idx;
}

void curata_device_expirate(uint64_t now) {
    for (int i = 0; i < MAX_DEVICES; i++) {
        if (devices[i].activ && (now - devices[i].last_seen) > ALERT_TIMEOUT_MS) {
            printf("TIMEOUT device [%d]: " MACSTR "\n", i, MAC2STR(devices[i].mac));
            devices[i].activ          = false;
            devices[i].kf_initialized = false;
            memset(devices[i].mac, 0, 6);
        }
    }
}

static bool adv_data_find_name(uint8_t *adv_data, uint8_t len, const char *target) {
    uint8_t *p    = adv_data;
    uint8_t  left = len;
    while (left > 0) {
        uint8_t field_len  = *p++; left--;
        if (field_len == 0 || left < field_len) break;
        uint8_t field_type = *p++; left--; field_len--;
        if (field_type == 0x09 || field_type == 0x08) {
            if (field_len == strlen(target) && memcmp(p, target, field_len) == 0)
                return true;
        }
        p    += field_len;
        left -= field_len;
    }
    return false;
}
char *get_name(uint8_t *adv_data, uint8_t len, char *name_buf, size_t buf_size) {
    uint8_t *p    = adv_data;
    uint8_t  left = len;
    while (left > 0) {
        uint8_t field_len  = *p++; left--;
        if (field_len == 0 || left < field_len) break;
        uint8_t field_type = *p++; left--; field_len--;
        if (field_type == 0x09 || field_type == 0x08) {
            if (field_len < buf_size) {
                memcpy(name_buf, p, field_len);
                name_buf[field_len] = '\0';
                return name_buf;
            }
        }
        p    += field_len;
        left -= field_len;
    }
    return "Unnamed";
}


uint16_t get_manufacturer_id(uint8_t *adv_data, uint8_t len) {
    uint8_t *p    = adv_data;
    uint8_t  left = len;
    while (left > 0) {
        uint8_t field_len  = *p++; left--;
        if (field_len == 0 || left < field_len) break;
        uint8_t field_type = *p++; left--; field_len--;
        if (field_type == 0xFF && field_len >= 2)
            return p[0] | (p[1] << 8);
        p    += field_len;
        left -= field_len;
    }
    return 0xFFFF;
}


void OnDataSent(const wifi_tx_info_t *txInfo, esp_now_send_status_t status) {
    if (status != ESP_NOW_SEND_SUCCESS)
        printf("ESP-NOW send failed\n");
}

void send_espnow_start() {
    if (mesaj_sent) return;
    esp_now_start_t msg = {0};
    msg.tip   = 0;
    msg.start = true;
    snprintf(msg.Nod, sizeof(msg.Nod), NOD_ID);
    esp_now_send(broadcastAddress, (uint8_t *)&msg, sizeof(msg));
    mesaj_sent = true;
    printf("Start calibrare trimis\n");
}

void send_espnow_calibration(bool calib_status, float rssi_1m) {
    esp_now_calib_t cal = {0};
    cal.tip   = 1;
    cal.calib = calib_status;
    if(calib_status)
        cal.rssi_1m = rssi_1m;
    else
        cal.rssi_1m = 0.0f;
    snprintf(cal.Nod, sizeof(cal.Nod), NOD_ID);
    esp_now_send(broadcastAddress, (uint8_t *)&cal, sizeof(cal));
    printf("Calibrare trimisa: %s\n", calib_status ? "TRUE" : "FALSE");
    if(calib_status) {
        printf("Referinta 1m : %.2f dBm\n",cal.rssi_1m);
    }
}

void send_espnow_alert(uint8_t *mac, uint8_t addr_type, uint16_t mfg,
                       const char *dev_name) {
    esp_now_alerta_t alert = {0};
    alert.tip       = 3;
    alert.addr_type = addr_type;
    alert.mfg_id    = mfg;
    snprintf(alert.Nod, sizeof(alert.Nod), NOD_ID);
    memcpy(alert.Mac, mac, 6);
 
    if (dev_name && dev_name[0] != '\0') {
        snprintf(alert.device_name, sizeof(alert.device_name), "%s", dev_name);
    } else {
        /* fara nume in advertising — marcam explicit */
        snprintf(alert.device_name, sizeof(alert.device_name), "[unnamed]");
    }
 
    esp_now_send(broadcastAddress, (uint8_t *)&alert, sizeof(alert));
    printf("Alerta trimisa: " MACSTR " | Tip:%d | MFG:0x%04X | Nume: %s\n",
           MAC2STR(mac), addr_type, mfg, alert.device_name);
}


void snapshot_timer_cb(void *arg) {
    
    int active_idx[MAX_DEVICES];
    int active_count = 0;

    for (int i = 0; i < MAX_DEVICES; i++)
        if (devices[i].activ)
            active_idx[active_count++] = i;

    if (active_count == 0) return;

    int total_chunks = (active_count + MAX_DEVICES_PER_PACKET - 1) / MAX_DEVICES_PER_PACKET;

    for (int c = 0; c < total_chunks; c++) {
        esp_now_snapshot_t snap = {0};
        snap.tip         = 2;
        snap.chunk_index = c;
        snap.chunk_total = total_chunks;
        snap.count       = 0;
        snprintf(snap.Nod, sizeof(snap.Nod), NOD_ID);

        int start = c * MAX_DEVICES_PER_PACKET;
        int end   = start + MAX_DEVICES_PER_PACKET;
        if (end > active_count) end = active_count;

        uint64_t now_us = esp_timer_get_time();

for (int i = start; i < end; i++) {
    int d = active_idx[i];  

    bool delta_semnificativ = fabsf(devices[d].last_rssi_filtrat - devices[d].last_sent_rssi) > 2.0f;
    bool heartbeat = (now_us - devices[d].last_sent_ts) > 5000000ULL; 

    if (!delta_semnificativ && !heartbeat) continue;

    devices[d].last_sent_rssi = devices[d].last_rssi_filtrat;
    devices[d].last_sent_ts   = now_us;

    memcpy(snap.devices[snap.count].mac, devices[d].mac, 6);
    snap.devices[snap.count].last_rssi_filtrat = devices[d].last_rssi_filtrat;
    snap.count++;
}
        if (snap.count == 0) continue;
        esp_now_send(broadcastAddress, (uint8_t *)&snap, sizeof(esp_now_snapshot_t));
        vTaskDelay(pdMS_TO_TICKS(CHUNK_DELAY_MS));
    }
}


static void esp_gap_cb(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {

    if (event == ESP_GAP_BLE_SCAN_PARAM_SET_COMPLETE_EVT) {
        esp_ble_gap_start_scanning(0);
        return;
    }

    if (event != ESP_GAP_BLE_SCAN_RESULT_EVT) return;
    if (param->scan_rst.search_evt != ESP_GAP_SEARCH_INQ_RES_EVT) return;

    int      raw_rssi = param->scan_rst.rssi;
    uint64_t now      = esp_timer_get_time() / 1000;

    if (!is_calibrated) {
        if (!adv_data_find_name(param->scan_rst.ble_adv,
                                param->scan_rst.adv_data_len,
                                TARGET_DEVICE_NAME)) return;

        send_espnow_start();

        calibration_sum    += raw_rssi;
        calibration_sq_sum += (float)raw_rssi * raw_rssi;
        calibration_count++;

        printf("CALIBRARE... %d/%d (Raw RSSI: %d)\n",
               calibration_count, CALIBRATION_SAMPLES, raw_rssi);

        if (calibration_count >= CALIBRATION_SAMPLES) {
            float mean     = calibration_sum / (float)CALIBRATION_SAMPLES;
            float variance = (calibration_sq_sum / (float)CALIBRATION_SAMPLES) - (mean * mean);
            if (variance < 0.1f) variance = 0.1f;

            dynamic_rssi_1m     = mean;
            measurement_noise_R = variance;

            is_calibrated = true;
            send_espnow_calibration(is_calibrated, dynamic_rssi_1m);

            esp_timer_start_periodic(snap_timer, SNAPSHOT_INTERVAL_MS * 1000);

            printf("\n--- CALIBRARE COMPLETA ---\n");
            printf("Referinta 1m : %.2f dBm\n", dynamic_rssi_1m);
            printf("Zgomot R     : %.4f\n", measurement_noise_R);
            printf("--------------------------\n\n");
        }
        return;
    }

    uint8_t *mac = param->scan_rst.bda;
    int      idx = gaseste_device(mac);
    if (raw_rssi <= RSSI_THRESHOLD) {return;
    }
    if (idx == -1) {
        idx = gaseste_loc_liber();   /* always returns a valid slot now */
        char name[MAX_DEVICE_NAME_LEN] = {0};
        get_name(param->scan_rst.ble_adv, param->scan_rst.adv_data_len, name, sizeof(name));
        memcpy(devices[idx].mac, mac, 6);
        devices[idx].activ          = true;
        devices[idx].last_seen      = now;
        devices[idx].last_rssi_filtrat = (float)raw_rssi;
        devices[idx].last_sent_rssi    = (float)raw_rssi; 
        devices[idx].last_sent_ts   = 0;
        devices[idx].kf_initialized = true;
        devices[idx].has_name       = (name[0] != '\0');
        kalman_init(&devices[idx].kf, PROCESS_NOISE, measurement_noise_R, (float)raw_rssi);

        uint16_t mfg = get_manufacturer_id(param->scan_rst.ble_adv,
                                           param->scan_rst.adv_data_len);
        send_espnow_alert(mac, param->scan_rst.ble_addr_type, mfg, name);
        printf("DEVICE NOU [%d]: " MACSTR " | Nume: %s\n",
               idx, MAC2STR(mac), name[0] ? name : "[unnamed]");
    } else if (!devices[idx].has_name) {
        /* Device already tracked but we never got its name — try again now */
        char name[MAX_DEVICE_NAME_LEN] = {0};
        get_name(param->scan_rst.ble_adv, param->scan_rst.adv_data_len, name, sizeof(name));
        if (name[0] != '\0') {
            devices[idx].has_name = true;
            uint16_t mfg = get_manufacturer_id(param->scan_rst.ble_adv,
                                               param->scan_rst.adv_data_len);
            /* Re-send alert so the Python side can update its registry */
            send_espnow_alert(mac, param->scan_rst.ble_addr_type, mfg, name);
            printf("DEVICE NUME ACTUALIZAT [%d]: " MACSTR " | Nume: %s\n",
                   idx, MAC2STR(mac), name);
        }
    }

    /* actualizam datele */
    float filtered_rssi        = kalman_update(&devices[idx].kf, (float)raw_rssi);
    devices[idx].last_rssi_filtrat = filtered_rssi;
    devices[idx].last_seen     = now;

    printf("[%d] " MACSTR " RSSI:%d Filtrat:%.2f\n",
       idx, MAC2STR(mac), raw_rssi, filtered_rssi);

    /* curatam device-urile expirate */
    curata_device_expirate(now);
}

/* ================================================================== */
/*  APP MAIN                                                            */
/* ================================================================== */
void app_main(void) {
    /* NVS */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* init device list */
    memset(devices, 0, sizeof(devices));

    /* WiFi + ESP-NOW */
    ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT));
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_send_cb(OnDataSent));

    memset(&peerInfo, 0, sizeof(peerInfo));
    memcpy(peerInfo.peer_addr, broadcastAddress, 6);
    peerInfo.channel = 0;
    peerInfo.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peerInfo));

    esp_timer_create_args_t timer_args = {
        .callback = snapshot_timer_cb,
        .name     = "snapshot"
    };
    ESP_ERROR_CHECK(esp_timer_create(&timer_args, &snap_timer));

    /* BT */
    esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_bt_controller_init(&bt_cfg));
    ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_BLE));
    ESP_ERROR_CHECK(esp_bluedroid_init());
    ESP_ERROR_CHECK(esp_bluedroid_enable());
    ESP_ERROR_CHECK(esp_ble_gap_register_callback(esp_gap_cb));
    ESP_ERROR_CHECK(esp_ble_gap_set_scan_params(&ble_scan_params));

    printf("--- SYSTEM READY – asteptam calibrare ---\n");
}