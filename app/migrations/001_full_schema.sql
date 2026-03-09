-- Price Monitor Pro: Full Schema Migration
-- Users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_chat_id VARCHAR(50) UNIQUE,
    username VARCHAR(255),
    timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    digest_frequency VARCHAR(20) DEFAULT 'none',
    digest_time TIME DEFAULT '09:00',
    digest_day_of_week INTEGER DEFAULT 1,
    default_check_interval INTEGER DEFAULT 300,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- API Keys
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    key_prefix VARCHAR(8) NOT NULL,
    name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Monitors
CREATE TABLE IF NOT EXISTS monitors (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    url TEXT NOT NULL,
    normalized_url TEXT,
    css_selector VARCHAR(500),
    xpath_selector VARCHAR(500),
    js_expression TEXT,
    currency VARCHAR(10) DEFAULT 'RUB',
    target_currency VARCHAR(10),
    threshold_below NUMERIC(12,2),
    threshold_above NUMERIC(12,2),
    threshold_pct NUMERIC(8,4),
    check_interval INTEGER DEFAULT 300,
    is_active BOOLEAN DEFAULT true,
    last_price NUMERIC(12,2),
    last_raw_text TEXT,
    last_checked TIMESTAMP,
    availability_status VARCHAR(20),
    availability_selector VARCHAR(500),
    availability_patterns TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    last_error TEXT,
    template_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Screenshots
CREATE TABLE IF NOT EXISTS screenshots (
    id SERIAL PRIMARY KEY,
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    image_data BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Price history
CREATE TABLE IF NOT EXISTS price_history (
    id SERIAL PRIMARY KEY,
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    price NUMERIC(12,2),
    raw_text TEXT,
    availability_status VARCHAR(20),
    screenshot_id INTEGER REFERENCES screenshots(id) ON DELETE SET NULL,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- Alert conditions
CREATE TABLE IF NOT EXISTS alert_conditions (
    id SERIAL PRIMARY KEY,
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    value NUMERIC(12,2),
    operator VARCHAR(5),
    parent_condition_id INTEGER REFERENCES alert_conditions(id) ON DELETE CASCADE,
    cooldown_seconds INTEGER DEFAULT 3600,
    is_active BOOLEAN DEFAULT true,
    last_triggered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Alerts log
CREATE TABLE IF NOT EXISTS alerts_log (
    id SERIAL PRIMARY KEY,
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    condition_id INTEGER REFERENCES alert_conditions(id) ON DELETE SET NULL,
    alert_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    old_price NUMERIC(12,2),
    new_price NUMERIC(12,2),
    change_pct NUMERIC(8,4),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Notification channels
CREATE TABLE IF NOT EXISTS notification_channels (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    channel_type VARCHAR(20) NOT NULL,
    config TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tags
CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS monitor_tags (
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (monitor_id, tag_id)
);

-- Comparison groups
CREATE TABLE IF NOT EXISTS comparison_groups (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS comparison_group_monitors (
    group_id INTEGER REFERENCES comparison_groups(id) ON DELETE CASCADE,
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, monitor_id)
);

-- Macros
CREATE TABLE IF NOT EXISTS macros (
    id SERIAL PRIMARY KEY,
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    selector VARCHAR(500),
    params TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Monitor templates
CREATE TABLE IF NOT EXISTS monitor_templates (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) UNIQUE NOT NULL,
    store_name VARCHAR(255) NOT NULL,
    css_selector VARCHAR(500),
    xpath_selector VARCHAR(500),
    currency VARCHAR(10) DEFAULT 'RUB',
    availability_patterns TEXT,
    created_by INTEGER REFERENCES users(id),
    is_system BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE monitors DROP CONSTRAINT IF EXISTS fk_monitors_template;
ALTER TABLE monitors ADD CONSTRAINT fk_monitors_template
    FOREIGN KEY (template_id) REFERENCES monitor_templates(id) ON DELETE SET NULL;

-- Queued alerts
CREATE TABLE IF NOT EXISTS queued_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    price NUMERIC(12,2),
    queued_at TIMESTAMP DEFAULT NOW()
);

-- Schema migrations tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) UNIQUE NOT NULL,
    applied_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_monitors_user ON monitors(user_id);
CREATE INDEX IF NOT EXISTS idx_monitors_normalized_url ON monitors(normalized_url);
CREATE INDEX IF NOT EXISTS idx_monitors_active ON monitors(is_active);
CREATE INDEX IF NOT EXISTS idx_ph_monitor ON price_history(monitor_id);
CREATE INDEX IF NOT EXISTS idx_ph_recorded ON price_history(recorded_at);
CREATE INDEX IF NOT EXISTS idx_ph_monitor_time ON price_history(monitor_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts_log(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_monitor ON alerts_log(monitor_id);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts_log(created_at);
CREATE INDEX IF NOT EXISTS idx_screenshots_monitor ON screenshots(monitor_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_nc_user ON notification_channels(user_id);
CREATE INDEX IF NOT EXISTS idx_nc_monitor ON notification_channels(monitor_id);
CREATE INDEX IF NOT EXISTS idx_macros_monitor ON macros(monitor_id, step_order);
CREATE INDEX IF NOT EXISTS idx_queued_user ON queued_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_templates_domain ON monitor_templates(domain);
