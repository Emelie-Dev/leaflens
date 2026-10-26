CREATE TABLE tbl_users (
  user_id INT NOT NULL AUTO_INCREMENT,
  first_name VARCHAR(50) NOT NULL,
  last_name VARCHAR(50) NOT NULL,
  email VARCHAR(100) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  phone_number VARCHAR(20) NULL,
  role ENUM('farmer','extension_worker') NOT NULL DEFAULT 'farmer',
  date_registered DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id),
  UNIQUE KEY uq_users_email (email)
);

CREATE TABLE tbl_administrators (
  admin_id INT NOT NULL AUTO_INCREMENT,
  first_name VARCHAR(50) NOT NULL,
  last_name VARCHAR(50) NOT NULL,
  email VARCHAR(100) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  date_added DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (admin_id),
  UNIQUE KEY uq_admin_email (email)
);

CREATE TABLE tbl_disease (
  disease_id INT NOT NULL AUTO_INCREMENT,
  class_label VARCHAR(150) NOT NULL,
  disease_name VARCHAR(100) NOT NULL,
  crop_name VARCHAR(100) NOT NULL,
  is_healthy TINYINT(1) NOT NULL DEFAULT 0,
  description TEXT NULL,
  recommended_treatment TEXT NULL,
  PRIMARY KEY (disease_id),
  UNIQUE KEY uq_disease_label (class_label)
);

CREATE TABLE tbl_model_version (
  model_id INT NOT NULL AUTO_INCREMENT,
  model_version VARCHAR(50) NOT NULL,
  accuracy FLOAT NOT NULL,
  date_deployed DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (model_id)
);

CREATE TABLE tbl_diagnosis_request (
  request_id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  image_path VARCHAR(255) NOT NULL,
  crop_type VARCHAR(100) NULL,
  upload_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status ENUM('pending','completed','failed') NOT NULL DEFAULT 'pending',
  PRIMARY KEY (request_id),
  CONSTRAINT fk_request_user FOREIGN KEY (user_id)
    REFERENCES tbl_users (user_id) ON DELETE CASCADE
);

CREATE TABLE tbl_prediction_result (
  result_id INT NOT NULL AUTO_INCREMENT,
  request_id INT NOT NULL,
  disease_id INT NOT NULL,
  model_id INT NOT NULL,
  confidence_score FLOAT NOT NULL,
  predicted_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (result_id),
  UNIQUE KEY uq_result_request (request_id),
  CONSTRAINT fk_result_request FOREIGN KEY (request_id)
    REFERENCES tbl_diagnosis_request (request_id) ON DELETE CASCADE,
  CONSTRAINT fk_result_disease FOREIGN KEY (disease_id)
    REFERENCES tbl_disease (disease_id),
  CONSTRAINT fk_result_model FOREIGN KEY (model_id)
    REFERENCES tbl_model_version (model_id)
);