<?php
namespace local_difodscopilot;

defined('MOODLE_INTERNAL') || die();

class observer {
    public static function submission_changed(\core\event\base $event): void {
        global $DB, $CFG;

        if (!self::course_enabled((int)$event->courseid)) {
            return;
        }

        $submissionid = (int)($event->objectid ?? 0);
        if (!$submissionid) {
            return;
        }

        $submission = $DB->get_record('assign_submission', ['id' => $submissionid], '*', IGNORE_MISSING);
        if (!$submission) {
            return;
        }

        $course = $DB->get_record('course', ['id' => $event->courseid], 'id,fullname', MUST_EXIST);
        $eventuuid = self::uuidv4();
        $correlationid = self::uuidv4();
        $measurement = stripos($course->fullname, 'final') !== false ? 'LF' : 'LB';
        $eventtype = $submission->status === 'submitted'
            ? 'submission.finalized'
            : 'submission.updated';

        $payload = [
            'event_id' => $eventuuid,
            'event_type' => $eventtype,
            'occurred_at' => gmdate('c', (int)$event->timecreated),
            'moodle_site_id' => hash('sha256', $CFG->wwwroot),
            'course_id' => (int)$event->courseid,
            'course_name' => $course->fullname,
            'submission_id' => $submissionid,
            'teacher_pseudonym_id' => 'tch_' . hash_hmac('sha256', (string)$submission->userid, $CFG->passwordsaltmain),
            'measurement' => $measurement,
            'manifest_version' => max(1, (int)$submission->attemptnumber + 1),
            'manifest_url' => null,
            'correlation_id' => $correlationid,
        ];

        $record = (object)[
            'eventuuid' => $eventuuid,
            'eventtype' => $eventtype,
            'courseid' => (int)$event->courseid,
            'submissionid' => $submissionid,
            'userid' => (int)$submission->userid,
            'payloadjson' => json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE),
            'status' => 'PENDING',
            'attempts' => 0,
            'timecreated' => time(),
            'timemodified' => time(),
        ];
        $outboxid = $DB->insert_record('local_difodscopilot_outbox', $record);

        $task = new \local_difodscopilot\task\send_event();
        $task->set_custom_data(['outboxid' => $outboxid]);
        \core\task\manager::queue_adhoc_task($task, true);
    }

    public static function completion_updated(\core\event\base $event): void {
        // Reconciliation will inspect the final assignment state; no heavy work in the observer.
    }

    private static function course_enabled(int $courseid): bool {
        $configured = trim((string)get_config('local_difodscopilot', 'courseids'));
        if ($configured === '') {
            return false;
        }
        $ids = array_map('intval', array_filter(array_map('trim', explode(',', $configured))));
        return in_array($courseid, $ids, true);
    }

    private static function uuidv4(): string {
        $data = random_bytes(16);
        $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
        $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
        return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
    }
}
