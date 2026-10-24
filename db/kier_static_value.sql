-- 날짜 구분이 없는 정적 값(풍력 시공간 API: 위치·고도·방위각별 풍속가속비율). kier_map 스키마, 2026-10-23 추가.
USE kier_map;
CREATE TABLE IF NOT EXISTS kier_static_value (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  dataset_id  VARCHAR(30) NOT NULL,
  lat         DECIMAL(9,6) NOT NULL,
  lon         DECIMAL(9,6) NOT NULL,
  alti_m      SMALLINT NOT NULL,          -- 고도(m)
  azi_deg     SMALLINT NOT NULL,          -- 방위각(도), 30° 간격 30~360
  value       DOUBLE NULL,
  unit        VARCHAR(60) NOT NULL,
  collected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_ds_loc (dataset_id, lat, lon),
  CONSTRAINT fk_sv_ds FOREIGN KEY (dataset_id) REFERENCES kier_dataset(dataset_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
