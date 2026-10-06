<?php
namespace local_difodscopilot\task;

defined('MOODLE_INTERNAL') || die();

class retry_outbox extends \core\task\scheduled_task {
    public function get_name(): string {
        return get_string('taskretryoutbox', 'local_difodscopilot');
    }

    public function execute(): void {
        global $DB;
        $cutoff = time() - 120;
        $records = $DB->get_records_select(
            'local_difodscopilot_outbox',
            'status = :status AND timemodified < :cutoff AND attempts < :maxattempts',
            ['status' => 'PENDING', 'cutoff' => $cutoff, 'maxattempts' => 10],
            'timecreated ASC',
            'id',
            0,
            100
        );
        foreach ($records as $record) {
            $task = new send_event();
            $task->set_custom_data(['outboxid' => $record->id]);
            \core\task\manager::queue_adhoc_task($task, true);
        }
    }
}

