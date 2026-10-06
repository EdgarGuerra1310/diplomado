<?php
namespace local_difodscopilot\privacy;

defined('MOODLE_INTERNAL') || die();

class provider implements \core_privacy\local\metadata\provider {
    public static function get_metadata(\core_privacy\local\metadata\collection $collection): \core_privacy\local\metadata\collection {
        $collection->add_database_table(
            'local_difodscopilot_outbox',
            [
                'userid' => 'privacy:metadata',
                'submissionid' => 'privacy:metadata',
                'payloadjson' => 'privacy:metadata',
            ],
            'privacy:metadata'
        );
        $collection->add_external_location_link(
            'difodscopilot',
            ['pseudonymous_user_id' => 'privacy:metadata'],
            'privacy:metadata'
        );
        return $collection;
    }
}

