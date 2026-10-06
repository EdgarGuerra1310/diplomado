<?php
namespace local_difodscopilot\external;

defined('MOODLE_INTERNAL') || die();

use core_external\external_api;
use core_external\external_function_parameters;
use core_external\external_multiple_structure;
use core_external\external_single_structure;
use core_external\external_value;

class get_case_manifest extends external_api {
    public static function execute_parameters(): external_function_parameters {
        return new external_function_parameters([
            'submissionid' => new external_value(PARAM_INT, 'Assignment submission ID'),
        ]);
    }

    public static function execute(int $submissionid): array {
        global $DB;
        $params = self::validate_parameters(self::execute_parameters(), ['submissionid' => $submissionid]);
        $submission = $DB->get_record('assign_submission', ['id' => $params['submissionid']], '*', MUST_EXIST);
        $assign = $DB->get_record('assign', ['id' => $submission->assignment], '*', MUST_EXIST);
        $cm = get_coursemodule_from_instance('assign', $assign->id, $assign->course, false, MUST_EXIST);
        $context = \context_module::instance($cm->id);
        self::validate_context($context);
        require_capability('local/difodscopilot:exportmanifest', \context_system::instance());

        $fs = get_file_storage();
        $storedfiles = $fs->get_area_files(
            $context->id,
            'assignsubmission_file',
            'submission_files',
            $submission->id,
            'id ASC',
            false
        );
        $files = [];
        foreach ($storedfiles as $file) {
            $url = \moodle_url::make_webservice_pluginfile_url(
                $file->get_contextid(),
                $file->get_component(),
                $file->get_filearea(),
                $file->get_itemid(),
                $file->get_filepath(),
                $file->get_filename()
            );
            $files[] = [
                'filename' => $file->get_filename(),
                'mimetype' => $file->get_mimetype() ?: 'application/octet-stream',
                'filesize' => $file->get_filesize(),
                'contenthash' => $file->get_contenthash(),
                'downloadurl' => $url->out(false),
            ];
        }
        return [
            'submissionid' => (int)$submission->id,
            'courseid' => (int)$assign->course,
            'assignmentid' => (int)$assign->id,
            'userid' => (int)$submission->userid,
            'attemptnumber' => (int)$submission->attemptnumber,
            'timemodified' => (int)$submission->timemodified,
            'files' => $files,
        ];
    }

    public static function execute_returns(): external_single_structure {
        return new external_single_structure([
            'submissionid' => new external_value(PARAM_INT, 'Submission ID'),
            'courseid' => new external_value(PARAM_INT, 'Course ID'),
            'assignmentid' => new external_value(PARAM_INT, 'Assignment ID'),
            'userid' => new external_value(PARAM_INT, 'Internal user ID'),
            'attemptnumber' => new external_value(PARAM_INT, 'Attempt number'),
            'timemodified' => new external_value(PARAM_INT, 'Modified timestamp'),
            'files' => new external_multiple_structure(new external_single_structure([
                'filename' => new external_value(PARAM_FILE, 'File name'),
                'mimetype' => new external_value(PARAM_RAW, 'MIME type'),
                'filesize' => new external_value(PARAM_INT, 'File size'),
                'contenthash' => new external_value(PARAM_ALPHANUM, 'Moodle content hash'),
                'downloadurl' => new external_value(PARAM_URL, 'Token-compatible download URL'),
            ])),
        ]);
    }
}

