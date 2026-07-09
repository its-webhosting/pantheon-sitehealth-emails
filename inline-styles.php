<?php
require __DIR__ . '/vendor/autoload.php';

use Pelago\Emogrifier\CssInliner;

$infile = $argv[1];
$outfile = $argv[2];

$html = file_get_contents($infile);

// Emogrifier parses with libxml, which assumes ISO-8859-1 for any document that does not
// declare a charset -- and Emogrifier's own <meta charset> injection is suppressed by a
// Content-Type meta tag that lacks one.  A UTF-8 em dash then re-emerges as "&acirc;..."
// (Gmail shows "â€”").  Encoding every non-ASCII character as a numeric entity first makes
// the input pure ASCII, so libxml's charset guess cannot matter, whatever the caller sends.
// (Documents that DO declare utf-8 are unaffected; ASCII documents are untouched.)
$html = mb_encode_numericentity($html, [0x80, 0x10FFFF, 0, 0x1FFFFF], 'UTF-8');

$visualHtml = CssInliner::fromHtml($html)->inlineCss()->render();

file_put_contents($outfile, $visualHtml);

?>

