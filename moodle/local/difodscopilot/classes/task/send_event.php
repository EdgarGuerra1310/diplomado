<?php
namespace local_difodscopilot\task;

defined('MOODLE_INTERNAL') || die();

class send_event extends \core\task\adhoc_task {
    public function execute(): void {
        global $DB;

        $data = $this->get_custom_data();
        $record = $DB->get_record('local_difodscopilot_outbox', ['id' => $data->outboxid], '*', MUST_EXIST);
        if ($record->status === 'SENT') {
            return;
        }

        $endpoint = (string)get_config('local_difodscopilot', 'apiendpoint');
        $secret = (string)get_config('local_difodscopilot', 'webhooksecret');
        if ($endpoint === '' || $secret === '') {
            throw new \moodle_exception('Copilot endpoint or signing secret is not configured.');
        }

        $payload = json_decode($record->payloadjson, true, 512, JSON_THROW_ON_ERROR);
        $canonical = self::canonical_json($payload);
        $signature = hash_hmac('sha256', $canonical, $secret);

        $curl = new \curl();
        $options = [
            'CURLOPT_TIMEOUT' => 15,
            'CURLOPT_CONNECTTIMEOUT' => 5,
            'CURLOPT_HTTPHEADER' => [
                'Content-Type: application/json',
                'X-Moodle-Signature: ' . $signature,
                'X-Correlation-ID: ' . $payload['correlation_id'],
            ],
        ];

        $record->attempts++;
        $record->timemodified = time();
        try {
            $curl->post($endpoint, $canonical, $options);
            $info = $curl->get_info();
            $httpcode = (int)($info['http_code'] ?? 0);
            if ($httpcode < 200 || $httpcode >= 300) {
                throw new \runtime_exception('Copilot returned HTTP ' . $httpcode);
            }
            $record->status = 'SENT';
            $record->lasterror = null;
            $DB->update_record('local_difodscopilot_outbox', $record);
        } catch (\Throwable $error) {
            $record->status = 'PENDING';
            $record->lasterror = substr($error->getMessage(), 0, 4000);
            $DB->update_record('local_difodscopilot_outbox', $record);
            throw $error;
        }
    }

    private static function canonical_json(array $value): string {
        self::sort_recursive($value);
        return json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    }

    private static function sort_recursive(array &$value): void {
        foreach ($value as &$item) {
            if (is_array($item)) {
                self::sort_recursive($item);
            }
        }
        if (array_keys($value) !== range(0, count($value) - 1)) {
            ksort($value);
        }
    }
}

