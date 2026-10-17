#!/usr/bin/env node
// Compile a LESS file to CSS on stdout, for the static build ("make static").
//
// tippr's stylesheets need LESS 1.4, but less 1.4's own command-line tool
// prints nothing on current Node.js versions, so this calls the library
// directly. The installer runs it with NODE_PATH pointing at the pinned
// less@1.4.2 install.
//
// usage: node scripts/lessc.js file.less > file.css

const fs = require("fs");
const path = require("path");
const less = require("less");

const file = process.argv[2];
if (!file) {
  console.error("usage: lessc.js file.less");
  process.exit(2);
}

const parser = new less.Parser({
  paths: [path.dirname(file)],
  filename: file,
});

parser.parse(fs.readFileSync(file, "utf8"), (err, tree) => {
  if (err) {
    console.error(`${err.filename}:${err.line}: ${err.message}`);
    process.exit(1);
  }
  let css;
  try {
    css = tree.toCSS();
  } catch (e) {
    console.error(`${e.filename || file}:${e.line || "?"}: ${e.message}`);
    process.exit(1);
  }
  process.stdout.write(css);
});
