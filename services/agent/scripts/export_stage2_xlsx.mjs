import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile, FileBlob } from "@oai/artifact-tool";

const [inputPath, outputPath, templatePath] = process.argv.slice(2);
const data = JSON.parse(await fs.readFile(inputPath, "utf8"));
if (data.headers.length !== 14 || data.headers[10] !== "色标") throw new Error("Expected 14 columns");
if (data.rows.some(row => row.length !== 14 || row[10] !== null)) throw new Error("Color must remain empty");
const directory = path.dirname(outputPath);
await fs.mkdir(directory, { recursive: true });
const reference = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
try {
  const preview = await reference.render({ sheetName: "Sheet1", range: "A1:L7", scale: 1.5, format: "png" });
  await fs.writeFile(path.join(directory, "reference_preview.png"), new Uint8Array(await preview.arrayBuffer()));
} catch (error) {
  console.log(`Reference preview unavailable: ${error.name}`);
}
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Sheet1");
const count = data.rows.length + 1;
const grid = sheet.getRange(`A1:N${count}`);
const literal = value => typeof value === "string" && value.startsWith("=") ? `'${value}` : value;
grid.values = [data.headers, ...data.rows.map(row => row.map(literal))];
grid.format.font = { name: data.style.font, size: data.style.size, color: "#000000" };
grid.format.borders = { preset: "all", style: "thin", color: "#000000" };
grid.format.fill = "#FFFFFF";
grid.format.wrapText = true;
grid.format.verticalAlignment = "top";
grid.format.rowHeight = data.style.body_height;
sheet.getRange("A1:N1").format.fill = data.style.header_fill;
sheet.getRange("A1:N1").format.font = { name: data.style.font, size: data.style.size, bold: true, color: "#000000" };
sheet.getRange("A1:N1").format.horizontalAlignment = "center";
sheet.getRange("A1:N1").format.verticalAlignment = "center";
for (let index = 0; index < 14; index++) {
  const letter = String.fromCharCode(65 + index);
  sheet.getRange(`${letter}1:${letter}${count}`).format.columnWidth = data.style.widths[index];
  if (index !== 9) sheet.getRange(`${letter}1:${letter}${count}`).setNumberFormat("@");
}
if (count > 1) {
  sheet.getRange(`J2:J${count}`).format.horizontalAlignment = "right";
  sheet.getRange(`L2:L${count}`).format.font = { name: data.style.font, size: 11, color: "#000000" };
  sheet.getRange(`A2:N${count}`).format.autofitRows();
}
sheet.freezePanes.freezeRows(1);
workbook.recalculate();
const inspected = await workbook.inspect({ kind: "table", range: "Sheet1!A1:N6", include: "values,formulas", tableMaxRows: 6, tableMaxCols: 14, maxChars: 3000 });
await fs.writeFile(path.join(directory, "xlsx-inspection.ndjson"), inspected.ndjson);
const preview = await workbook.render({ sheetName: "Sheet1", range: `A1:N${Math.min(count, 10)}`, scale: 1.5, format: "png" });
await fs.writeFile(path.join(directory, "result_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`XLSX exported: ${data.rows.length} rows, 14 columns, empty color column`);
