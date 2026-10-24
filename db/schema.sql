CREATE DATABASE IF NOT EXISTS kier_map DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE kier_map;

-- KIER 7종 데이터 카탈로그
CREATE TABLE IF NOT EXISTS kier_dataset (
  dataset_id   VARCHAR(30) PRIMARY KEY,
  name_ko      VARCHAR(100) NOT NULL,
  kind         ENUM('api','file') NOT NULL,
  data_go_id   VARCHAR(20) NOT NULL,
  source_url   VARCHAR(300) NOT NULL,
  unit         VARCHAR(40) NULL,
  period_note  VARCHAR(100) NULL,
  status       ENUM('not_started','collecting','ready','demo') NOT NULL DEFAULT 'not_started',
  status_label VARCHAR(30) NOT NULL DEFAULT '준비 중',
  updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 위치·기간별 값 (수집·가공 결과)
CREATE TABLE IF NOT EXISTS kier_point_value (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  dataset_id  VARCHAR(30) NOT NULL,
  lat         DECIMAL(9,6) NOT NULL,
  lon         DECIMAL(9,6) NOT NULL,
  period_start DATE NOT NULL,
  period_end   DATE NOT NULL,
  metric      VARCHAR(60) NOT NULL,
  value       DOUBLE NULL,
  unit        VARCHAR(40) NOT NULL,
  is_demo     TINYINT(1) NOT NULL DEFAULT 0,
  collected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_ds_loc (dataset_id, lat, lon),
  KEY ix_ds_period (dataset_id, period_start, period_end),
  CONSTRAINT fk_pv_ds FOREIGN KEY (dataset_id) REFERENCES kier_dataset(dataset_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
