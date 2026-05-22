CREATE TABLE currency (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    symbol TEXT NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    decimals INT DEFAULT 2,
    decimal_separator TEXT,
    group_separator TEXT,
    symbol_format TEXT DEFAULT 'RS',
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE category (
    id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    "left" INT DEFAULT 0,
    "right" INT DEFAULT 0,
    type INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE project (
    id BIGINT PRIMARY KEY,
    title TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE payee (
    id BIGINT PRIMARY KEY,
    title TEXT,
    last_category_id BIGINT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE location (
    id BIGINT PRIMARY KEY,
    title TEXT,
    datetime BIGINT NOT NULL,
    provider TEXT,
    accuracy REAL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    resolved_address TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    creation_date BIGINT NOT NULL,
    currency_id BIGINT NOT NULL REFERENCES currency(id),
    total_amount BIGINT DEFAULT 0,
    sort_order INT DEFAULT 0,
    type TEXT DEFAULT 'CASH',
    issuer TEXT,
    number TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    is_include_into_totals BOOLEAN DEFAULT TRUE,
    last_category_id BIGINT DEFAULT 0,
    last_account_id BIGINT DEFAULT 0,
    total_limit BIGINT DEFAULT 0,
    card_issuer TEXT,
    closing_day INT DEFAULT 0,
    payment_day INT DEFAULT 0,
    note TEXT,
    last_transaction_date BIGINT DEFAULT 0
);

CREATE TABLE transaction (
    id BIGINT PRIMARY KEY,
    from_account_id BIGINT NOT NULL REFERENCES account(id),
    to_account_id BIGINT DEFAULT 0,
    category_id BIGINT DEFAULT 0,
    project_id BIGINT DEFAULT 0,
    location_id BIGINT DEFAULT 0,
    payee_id BIGINT DEFAULT 0,
    note TEXT,
    from_amount BIGINT DEFAULT 0,
    to_amount BIGINT DEFAULT 0,
    datetime BIGINT NOT NULL,
    original_currency_id BIGINT DEFAULT 0,
    original_from_amount BIGINT DEFAULT 0,
    parent_id BIGINT DEFAULT 0,
    is_template INT DEFAULT 0,
    template_name TEXT,
    recurrence TEXT,
    status TEXT DEFAULT 'UR',
    is_ccard_payment INT DEFAULT 0,
    last_recurrence BIGINT DEFAULT 0
);

CREATE TABLE attribute (
    id BIGINT PRIMARY KEY,
    type INT DEFAULT 1,
    title TEXT,
    list_values TEXT,
    default_value TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE category_attribute (
    category_id BIGINT NOT NULL REFERENCES category(id),
    attribute_id BIGINT NOT NULL REFERENCES attribute(id),
    PRIMARY KEY (category_id, attribute_id)
);

CREATE TABLE transaction_attribute (
    transaction_id BIGINT NOT NULL REFERENCES transaction(id),
    attribute_id BIGINT NOT NULL REFERENCES attribute(id),
    value TEXT,
    PRIMARY KEY (transaction_id, attribute_id)
);

CREATE TABLE budget (
    id BIGINT PRIMARY KEY,
    title TEXT,
    category_id TEXT NOT NULL,
    currency_id BIGINT NOT NULL,
    amount BIGINT NOT NULL,
    include_subcategories INT DEFAULT 1,
    start_date BIGINT,
    end_date BIGINT,
    project_id TEXT,
    recur TEXT,
    recur_num INT DEFAULT 0,
    is_current INT DEFAULT 1,
    parent_budget_id BIGINT DEFAULT 0
);

CREATE TABLE currency_exchange_rate (
    from_currency_id BIGINT NOT NULL REFERENCES currency(id),
    to_currency_id BIGINT NOT NULL REFERENCES currency(id),
    rate_date BIGINT NOT NULL,
    rate REAL NOT NULL,
    PRIMARY KEY (from_currency_id, to_currency_id, rate_date)
);

CREATE TABLE ccard_closing_date (
    account_id BIGINT NOT NULL REFERENCES account(id),
    period INT NOT NULL,
    closing_day INT NOT NULL,
    PRIMARY KEY (account_id, period)
);

-- Indexes
CREATE INDEX idx_transaction_from_account ON transaction(from_account_id);
CREATE INDEX idx_transaction_datetime ON transaction(datetime);
CREATE INDEX idx_transaction_category ON transaction(category_id);
CREATE INDEX idx_transaction_payee ON transaction(payee_id);
CREATE INDEX idx_transaction_parent ON transaction(parent_id);
CREATE INDEX idx_account_currency ON account(currency_id);
