import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { parse } from "@babel/parser";

const page = readFileSync(new URL("./Templates.jsx", import.meta.url), "utf8");
const builder = readFileSync(new URL("../components/templates/TemplateBuilderModal.jsx", import.meta.url), "utf8");
const detail = readFileSync(new URL("./TemplateDetail.jsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../api/templateApi.js", import.meta.url), "utf8");
const pageAst = parse(page, { sourceType: "module", plugins: ["jsx"] });

function walk(node, visit) {
  if (!node || typeof node !== "object") return;
  visit(node);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach((item) => walk(item, visit));
    else if (value && typeof value === "object") walk(value, visit);
  }
}

function memberPath(node) {
  if (node?.type === "Identifier") return [node.name];
  if (node?.type !== "MemberExpression" && node?.type !== "OptionalMemberExpression") return null;
  const objectPath = memberPath(node.object);
  const property = node.computed
    ? node.property?.type === "StringLiteral" ? node.property.value : null
    : node.property?.type === "Identifier" ? node.property.name : null;
  return objectPath && property ? [...objectPath, property] : null;
}

function isTemplateDetailHref(attribute) {
  const expression = attribute?.value?.type === "JSXExpressionContainer" ? attribute.value.expression : null;
  if (expression?.type === "TemplateLiteral") {
    return expression.expressions.length === 1
      && expression.quasis.length === 2
      && expression.quasis[0].value.cooked === "#/templates/"
      && expression.quasis[1].value.cooked === ""
      && memberPath(expression.expressions[0])?.join(".") === "template.id";
  }
  return expression?.type === "BinaryExpression"
    && expression.operator === "+"
    && expression.left?.type === "StringLiteral"
    && expression.left.value === "#/templates/"
    && memberPath(expression.right)?.join(".") === "template.id";
}

function previewButtonsIn(collectionName) {
  const buttons = [];
  walk(pageAst, (node) => {
    if (node.type !== "CallExpression"
      || memberPath(node.callee)?.join(".") !== `${collectionName}.map`
      || !node.arguments[0]) return;
    walk(node.arguments[0], (child) => {
      if (child.type !== "JSXElement" || child.openingElement.name?.name !== "Button") return;
      const label = child.children
        .map((item) => item.type === "JSXText" ? item.value : item.expression?.type === "StringLiteral" ? item.expression.value : "")
        .join("")
        .trim();
      if (label !== "Önizle") return;
      buttons.push(child.openingElement.attributes.find((attribute) => attribute.type === "JSXAttribute" && attribute.name?.name === "href"));
    });
  });
  return buttons;
}

test("create opens a form without posting and submission is guarded", () => {
  assert.match(page, /setBuilderTemplate\(null\)/);
  assert.match(page, /submittingRef\.current/);
  assert.doesNotMatch(page, /name: "Yeni özel şablon"/);
  assert.match(builder, /onSubmit=\{submit\}/);
  assert.match(builder, /Şablon adı zorunludur/);
});

test("builder exposes canonical settings, preview, dirty warning, and duplicate feedback", () => {
  for (const key of ["layout", "columns", "rows", "slot_count", "page_format", "primary_color", "secondary_color", "price_style", "badge_style", "show_footer"]) assert.match(builder, new RegExp(key));
  assert.match(builder, /template-live-preview/);
  assert.match(builder, /beforeunload/);
  assert.match(builder, /Kaydedilmemiş değişiklikler/);
  assert.match(page, /Bu isimle bir şablon zaten mevcut/);
});

test("builder resets only when the create or edit target changes", () => {
  assert.match(builder, /const targetKey = template\?\.id \? `edit:\$\{template\.id\}` : "create"/);
  assert.match(builder, /useMemo\(\(\) => buildInitialForm\(template\), \[targetKey\]\)/);
  assert.match(builder, /setForm\(initial\);\s*setSubmitted\(false\);/);
  assert.doesNotMatch(builder, /\}, \[template\]\)/);
});

test("template detail gates editing for permissions and global templates", () => {
  assert.match(detail, /const canEdit = canManage && !template\.isGlobal/);
  assert.match(detail, /if \(!canEdit \|\| isSaving\) return/);
  assert.match(detail, /if \(canEdit\) setEditing\(true\)/);
  assert.match(detail, /\{canEdit && isEditing \? <TemplateBuilderModal/);
});

test("thumbnail upload falls back when the browser omits the file content type", () => {
  assert.match(api, /file\.type \|\| "application\/octet-stream"/);
});

test("global and market template previews use the hash-based SPA detail route", () => {
  const fullPageNavigations = [];
  walk(pageAst, (node) => {
    if (node.type === "AssignmentExpression" && memberPath(node.left)?.join(".") === "window.location.href") {
      fullPageNavigations.push(node);
    }
  });
  assert.equal(fullPageNavigations.length, 0, "template previews must not assign window.location.href");

  for (const collectionName of ["shared", "mine"]) {
    const previewButtons = previewButtonsIn(collectionName);
    assert.ok(previewButtons.length > 0, `${collectionName} templates must expose a preview button`);
    assert.ok(previewButtons.every(isTemplateDetailHref), `${collectionName} previews must use #/templates/\${template.id}`);
  }
});
