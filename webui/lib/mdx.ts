import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';

export interface DocFrontmatter {
	title: string;
	order?: number;
	audience?: 'beginner' | 'advanced' | 'both';
}

export interface Doc {
	frontmatter: DocFrontmatter;
	content: string;
	slug: string;
}

const DOCS_DIR = path.join(process.cwd(), 'content', 'docs');

export async function getDocBySlug(slug: string): Promise<Doc | null> {
	try {
		const docPath = path.join(DOCS_DIR, `${slug}.mdx`);
		const fileContent = fs.readFileSync(docPath, 'utf-8');
		const { data, content } = matter(fileContent);

		return {
			frontmatter: data as DocFrontmatter,
			content,
			slug,
		};
	} catch {
		return null;
	}
}

export async function getAllDocs(): Promise<Doc[]> {
	try {
		if (!fs.existsSync(DOCS_DIR)) {
			return [];
		}

		const files = fs.readdirSync(DOCS_DIR).filter(f => f.endsWith('.mdx'));
		const docs = files
			.map(file => {
				const slug = file.replace(/\.mdx$/, '');
				const filePath = path.join(DOCS_DIR, file);
				const fileContent = fs.readFileSync(filePath, 'utf-8');
				const { data, content } = matter(fileContent);

				return {
					slug,
					frontmatter: data as DocFrontmatter,
					content,
				};
			})
			.sort((a, b) => (a.frontmatter.order ?? 999) - (b.frontmatter.order ?? 999));

		return docs;
	} catch {
		return [];
	}
}
