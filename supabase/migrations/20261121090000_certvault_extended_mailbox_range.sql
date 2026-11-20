alter table private.mailbox_tokens drop constraint mailbox_tokens_scan_days_check;
alter table private.mailbox_tokens add constraint mailbox_tokens_scan_days_check check (scan_days between 1 and 3650);
