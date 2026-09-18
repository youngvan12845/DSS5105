"""Management command to enrich the 12 core articles with deep technical content while strictly preserving evaluation benchmark facts."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from a_agent.services.article_index import index_article
from a_blog.models import ArticlePage


ENRICHED_ARTICLES = {
    'python-basics-variables': {
        'intro': 'Fundamental Python syntax, dynamic typing, and memory model',
        'body': (
            '<h2>Introduction to Python Types</h2>'
            '<p>Python uses dynamic typing. Common types include int, float, str, list, and dict.</p>'
            '<p>Variables do not need type declarations — assign a value directly.</p>'
            '<p>In Python, every variable is a reference to an object stored in memory. When you write <code>x = 42</code>, '
            'Python allocates an integer object with value 42 and binds the identifier <code>x</code> to that object.</p>'
            '<h2>Core Data Types Overview</h2>'
            '<h3>Numeric Types</h3>'
            '<ul>'
            '<li><strong>int</strong>: Arbitrary precision integers (e.g., <code>100</code>, <code>-5</code>). Python 3 automatically handles large numbers without overflow.</li>'
            '<li><strong>float</strong>: 64-bit double-precision floating-point numbers adhering to IEEE 754 (e.g., <code>3.14159</code>, <code>1e-4</code>).</li>'
            '<li><strong>bool</strong>: Boolean subtype of int representing truth values (<code>True</code> and <code>False</code>).</li>'
            '</ul>'
            '<h3>Sequences and Collections</h3>'
            '<ul>'
            '<li><strong>str</strong>: Immutable sequence of Unicode characters. Supports slicing: <code>text[0:4]</code> and f-strings: <code>f"Hello {name}"</code>.</li>'
            '<li><strong>list</strong>: Mutable, ordered sequence of heterogeneous elements: <code>numbers = [1, 2, 3]</code>.</li>'
            '<li><strong>tuple</strong>: Immutable ordered sequence: <code>coords = (10.0, 20.0)</code>.</li>'
            '<li><strong>dict</strong>: Key-value hash map providing O(1) average lookup time: <code>user = {"id": 1, "role": "admin"}</code>.</li>'
            '</ul>'
            '<h2>Type Inspection and Conversion</h2>'
            '<p>You can inspect an object\'s runtime type using the built-in <code>type()</code> function, or verify inheritance with <code>isinstance()</code>:</p>'
            '<pre><code>value = "1024"\n'
            'print(type(value))  # &lt;class \'str\'&gt;\n'
            'number = int(value)\n'
            'print(isinstance(number, int))  # True</code></pre>'
            '<h2>Best Practices for Variable Naming</h2>'
            '<p>Follow PEP 8 conventions: use <code>snake_case</code> for variables and functions, <code>UPPER_SNAKE_CASE</code> for constants, '
            'and choose descriptive names that reveal intent without requiring inline comments.</p>'
        ),
    },
    'python-functions-modules': {
        'intro': 'Structuring scalable Python programs with functions and modules',
        'body': (
            '<h2>Defining Reusable Functions</h2>'
            '<p>Functions are defined with def. Modules split code across files and are imported with import.</p>'
            '<p>Good module structure helps maintenance and testing.</p>'
            '<p>A function encapsulates a specific computation or behavior, making your codebase modular, readable, and DRY (Don\'t Repeat Yourself).</p>'
            '<h2>Function Parameters and Return Values</h2>'
            '<p>Python supports positional arguments, default keyword arguments, and arbitrary argument lists via <code>*args</code> and <code>**kwargs</code>:</p>'
            '<pre><code>def calculate_metrics(y_true, y_pred, verbose=False, **options):\n'
            '    mse = sum((yt - yp) ** 2 for yt, yp in zip(y_true, y_pred)) / len(y_true)\n'
            '    if verbose:\n'
            '        print(f"Computed MSE: {mse:.4f}")\n'
            '    return mse, options.get("metadata", {})</code></pre>'
            '<h2>Scope Rules (LEGB)</h2>'
            '<p>Python resolves variable names using the LEGB rule in order:</p>'
            '<ol>'
            '<li><strong>Local (L)</strong>: Variables assigned inside the function body.</li>'
            '<li><strong>Enclosing (E)</strong>: Outer functions in nested closures.</li>'
            '<li><strong>Global (G)</strong>: Module-level variables defined at the file root.</li>'
            '<li><strong>Built-in (B)</strong>: Pre-assigned language keywords and functions like <code>len</code>, <code>range</code>.</li>'
            '</ol>'
            '<h2>Modules and Packages</h2>'
            '<p>Any Python source file (<code>.py</code>) acts as an importable module. When designing packages with multiple modules, '
            'include an <code>__init__.py</code> file to mark the directory as a Python package. Use <code>if __name__ == "__main__":</code> '
            'to ensure entry-point scripts only run when directly executed, rather than upon import.</p>'
        ),
    },
    'ml-supervised-unsupervised': {
        'intro': 'Core paradigms of modern machine learning algorithms',
        'body': (
            '<h2>The Two Primary Paradigms</h2>'
            '<p>Supervised learning trains on labeled data for tasks like classification and regression.</p>'
            '<p>Unsupervised learning finds structure in unlabeled data, such as clustering.</p>'
            '<p>Choosing the correct paradigm depends primarily on whether your dataset contains ground truth target labels (y) or only input features (X).</p>'
            '<h2>Supervised Learning in Depth</h2>'
            '<p>The algorithm learns a mapping function <code>f(X) -> y</code> by minimizing an empirical loss function computed against labeled training examples.</p>'
            '<ul>'
            '<li><strong>Regression</strong>: Predicting continuous quantities. Examples include housing prices, stock valuations, and temperature forecasting. '
            'Popular models include Ordinary Least Squares, Ridge, Lasso, and Gradient Boosting Regressors.</li>'
            '<li><strong>Classification</strong>: Predicting discrete category labels (binary or multiclass). Examples include spam detection, medical diagnostics, and image recognition. '
            'Common models include Logistic Regression, Support Vector Machines (SVM), and Random Forests.</li>'
            '</ul>'
            '<h2>Unsupervised Learning in Depth</h2>'
            '<p>Unsupervised methods discover latent patterns, probability densities, or grouping structures without external supervisor feedback:</p>'
            '<ul>'
            '<li><strong>Clustering</strong>: Partitioning instances into cohesive subgroups. K-Means optimizes intra-cluster distance, while DBSCAN identifies density-based spatial clusters.</li>'
            '<li><strong>Dimensionality Reduction</strong>: Projecting high-dimensional feature vectors into lower-dimensional space while retaining variance. '
            'Principal Component Analysis (PCA) and t-SNE are standard tools for visualization and noise filtering.</li>'
            '<li><strong>Anomaly Detection</strong>: Isolating statistical outliers using Isolation Forests or Gaussian Mixture Models (GMM).</li>'
            '</ul>'
            '<h2>Validation and Generalization</h2>'
            '<p>Always evaluate models on unseen holdout test sets or cross-validation folds to detect overfitting early. In supervised learning, '
            'metrics include Accuracy, Precision, Recall, F1-Score, and ROC-AUC. In unsupervised clustering, the Silhouette Score measures cluster separation.</p>'
        ),
    },
    'gradient-descent-intuition': {
        'intro': 'Mathematical intuition and mechanics behind first-order optimization',
        'body': (
            '<h2>What Is Gradient Descent?</h2>'
            '<p>Gradient descent updates parameters along the negative gradient of the loss to reduce error step by step.</p>'
            '<p>The learning rate controls how large each step is.</p>'
            '<p>It is the foundational optimization engine powering linear models, neural networks, and modern transformer architectures.</p>'
            '<h2>The Mountain Descent Analogy</h2>'
            '<p>Imagine standing in a dense fog on a steep mountain with zero visibility. To find the valley (global minimum of loss), '
            'you feel the slope of the ground under your feet. The direction of steepest ascent is the gradient vector <code>∇L(θ)</code>. '
            'By stepping in the exact opposite direction <code>-∇L(θ)</code>, you descend toward lower elevation.</p>'
            '<h2>The Parameter Update Rule</h2>'
            '<p>Mathematically, parameters θ are updated iteratively across iterations <code>t</code> according to:</p>'
            '<pre><code>θ_(t+1) = θ_t - η * ∇L(θ_t)</code></pre>'
            '<p>where <code>η</code> (eta) represents the learning rate.</p>'
            '<h2>The Learning Rate Dilemma</h2>'
            '<ul>'
            '<li><strong>Too large (η &gt;&gt; 0)</strong>: The algorithm overshoots the minimum, oscillating wildly and potentially diverging to infinity.</li>'
            '<li><strong>Too small (η &lt;&lt; 1)</strong>: Convergence becomes excruciatingly slow, requiring excessive compute and getting trapped in shallow local plateaus.</li>'
            '</ul>'
            '<h2>Variants: Batch, SGD, and Mini-Batch</h2>'
            '<p>Standard <strong>Batch Gradient Descent</strong> computes gradients across the entire dataset per step, which is computationally expensive on big data. '
            '<strong>Stochastic Gradient Descent (SGD)</strong> updates parameters using a single random sample per iteration, yielding fast but noisy trajectories. '
            'Modern deep learning utilizes <strong>Mini-Batch Gradient Descent</strong> (typically batch sizes of 32 to 512) paired with adaptive optimizers like Adam and RMSprop.</p>'
        ),
    },
    'linear-regression-practice': {
        'intro': 'Practical implementation and diagnostic evaluation of linear regression',
        'body': (
            '<h2>Linear Regression Fundamentals</h2>'
            '<p>Linear regression assumes a linear relationship between features and targets. You can train quickly with sklearn.</p>'
            '<p>Common metrics include MSE and R².</p>'
            '<p>Despite its conceptual simplicity, linear regression remains a baseline standard in data science due to its interpretability, '
            'computational efficiency, and analytical tractability.</p>'
            '<h2>Mathematical Formulation</h2>'
            '<p>The model expresses the target <code>y</code> as a weighted linear combination of independent input features <code>X</code> plus an intercept bias term <code>b</code>:</p>'
            '<pre><code>y = w_1*x_1 + w_2*x_2 + ... + w_n*x_n + b</code></pre>'
            '<p>The coefficients <code>w</code> are fitted by minimizing the sum of squared residuals (Ordinary Least Squares, OLS).</p>'
            '<h2>Implementation with Scikit-Learn</h2>'
            '<p>Training a model in Python requires only a few lines with <code>sklearn.linear_model</code>:</p>'
            '<pre><code>from sklearn.linear_model import LinearRegression\n'
            'from sklearn.metrics import mean_squared_error, r2_score\n'
            'from sklearn.model_selection import train_test_split\n\n'
            'X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)\n'
            'model = LinearRegression()\n'
            'model.fit(X_train, y_train)\n\n'
            'predictions = model.predict(X_test)\n'
            'mse = mean_squared_error(y_test, predictions)\n'
            'r2 = r2_score(y_test, predictions)\n'
            'print(f"Test MSE: {mse:.2f}, R2 Score: {r2:.3f}")</code></pre>'
            '<h2>Diagnostic Metrics Explained</h2>'
            '<ul>'
            '<li><strong>Mean Squared Error (MSE)</strong>: Averages squared prediction discrepancies. Heavily penalizes large outlier mistakes.</li>'
            '<li><strong>R² Score (Coefficient of Determination)</strong>: Quantifies the proportion of variance in the dependent variable explained by the features (1.0 is perfect, 0.0 equals baseline mean prediction).</li>'
            '</ul>'
            '<h2>Combatting Overfitting with Regularization</h2>'
            '<p>When dealing with multicollinearity or high feature counts, apply L2 regularization (<strong>Ridge Regression</strong>) '
            'or L1 regularization (<strong>Lasso Regression</strong>) which drives negligible feature weights toward zero for automatic feature selection.</p>'
        ),
    },
    'web-http-rest': {
        'intro': 'Core architectural principles of HTTP networking and RESTful API design',
        'body': (
            '<h2>The Foundation of Web Systems</h2>'
            '<p>HTTP is the protocol for web communication. REST uses resource-oriented URLs and verbs like GET, POST, PUT, and DELETE.</p>'
            '<p>Every interaction between a browser and a server follows this standardized stateless request-response paradigm.</p>'
            '<h2>The Anatomy of an HTTP Transaction</h2>'
            '<p>An HTTP request consists of three essential segments:</p>'
            '<ol>'
            '<li><strong>Request Line</strong>: The method verb, target URI path, and protocol version (e.g., <code>GET /api/articles/ HTTP/1.1</code>).</li>'
            '<li><strong>Headers</strong>: Metadata key-value pairs specifying content types, authentication tokens, caching directives, and cookies.</li>'
            '<li><strong>Body (Payload)</strong>: Optional payload data, typically formatted in JSON for RESTful endpoints.</li>'
            '</ol>'
            '<h2>Core HTTP Verbs and Idempotency</h2>'
            '<ul>'
            '<li><strong>GET</strong>: Retrieve resource representations. Safe and idempotent — does not modify server state.</li>'
            '<li><strong>POST</strong>: Create new subsidiary resources or submit form data. Neither safe nor idempotent.</li>'
            '<li><strong>PUT</strong>: Completely replace an existing resource identified by URI. Idempotent.</li>'
            '<li><strong>PATCH</strong>: Apply partial modifications to an existing resource.</li>'
            '<li><strong>DELETE</strong>: Remove the identified resource. Idempotent.</li>'
            '</ul>'
            '<h2>Standard HTTP Status Codes</h2>'
            '<p>Servers return 3-digit status codes indicating the result of the request:</p>'
            '<ul>'
            '<li><code>200 OK</code> / <code>201 Created</code>: Request processed successfully.</li>'
            '<li><code>301 Moved Permanently</code> / <code>302 Found</code>: Resource relocation and redirects.</li>'
            '<li><code>400 Bad Request</code> / <code>401 Unauthorized</code> / <code>403 Forbidden</code> / <code>404 Not Found</code>: Client-side errors.</li>'
            '<li><code>500 Internal Server Error</code> / <code>502 Bad Gateway</code>: Server-side runtime failures.</li>'
            '</ul>'
            '<h2>REST Architectural Constraints</h2>'
            '<p>Roy Fielding established that true REST services must maintain client-server separation, remain completely stateless across interactions, '
            'leverage standard HTTP cacheability, and utilize uniform resource identifiers (URIs) representing nouns rather than remote procedure verbs.</p>'
        ),
    },
    'django-project-structure': {
        'intro': 'Navigating Django application architecture and the MVT design pattern',
        'body': (
            '<h2>Django Architectural Blueprint</h2>'
            '<p>A Django project contains one project config and multiple apps. settings, urls, models, and views are the core pieces.</p>'
            '<p>Understanding this separation of concerns enables teams to scale web applications cleanly from simple prototypes to enterprise backends.</p>'
            '<h2>The MVT (Model-View-Template) Pattern</h2>'
            '<p>Django implements a pragmatic variant of the traditional MVC architecture:</p>'
            '<ul>'
            '<li><strong>Model (<code>models.py</code>)</strong>: The data access layer. Uses Django\'s built-in Object-Relational Mapper (ORM) to define database tables as Python classes.</li>'
            '<li><strong>View (<code>views.py</code>)</strong>: The business logic controller. Receives HTTP requests, queries models, and returns HTTP responses or rendered templates.</li>'
            '<li><strong>Template (<code>templates/</code>)</strong>: The presentation layout. Uses Django Template Language (DTL) to render dynamic data safely with automatic XSS escaping.</li>'
            '</ul>'
            '<h2>Directory Hierarchy Explained</h2>'
            '<pre><code>my_project/\n'
            '├── manage.py              # CLI entry point for migrations and dev server\n'
            '├── a_core/                # Project root configuration package\n'
            '│   ├── settings.py        # Global settings, installed apps, database config\n'
            '│   ├── urls.py            # Root URL dispatcher mapping paths to views\n'
            '│   └── wsgi.py            # WSGI interface for production web servers (Gunicorn)\n'
            '└── a_blog/                # Individual reusable application\n'
            '    ├── models.py          # Domain database models\n'
            '    ├── views.py           # Endpoint request handlers\n'
            '    ├── urls.py            # App-specific URL routes\n'
            '    └── migrations/        # Version-controlled schema migrations</code></pre>'
            '<h2>The Migration Lifecycle</h2>'
            '<p>Whenever you modify a model in <code>models.py</code>, execute <code>python manage.py makemigrations</code> to generate migration files, '
            'followed by <code>python manage.py migrate</code> to apply the schema alterations to PostgreSQL atomically.</p>'
        ),
    },
    'wagtail-quickstart': {
        'intro': 'Rapid enterprise content management built on top of Django',
        'body': (
            '<h2>What Is Wagtail CMS?</h2>'
            '<p>Wagtail builds on Django with a page tree and a friendly admin editing experience.</p>'
            '<p>Unlike monolithic content management systems, Wagtail does not lock you into rigid templates; it is a Pythonic Django package '
            'that allows developers complete control over models, queries, and presentation templates.</p>'
            '<h2>The Hierarchical Page Tree</h2>'
            '<p>Every page in Wagtail inherits from <code>wagtail.models.Page</code>. This structure automatically establishes parent-child '
            'tree relationships using treebeard, powers URL path routing, and manages access permissions across site hierarchies.</p>'
            '<h2>Custom Page Models and Panels</h2>'
            '<p>You define editorial fields and specify how they render inside the Wagtail admin dashboard using panels:</p>'
            '<pre><code>from wagtail.models import Page\n'
            'from wagtail.fields import RichTextField\n'
            'from wagtail.admin.panels import FieldPanel\n\n'
            'class TechArticlePage(Page):\n'
            '    intro = models.CharField(max_length=250)\n'
            '    body = RichTextField(blank=True)\n\n'
            '    content_panels = Page.content_panels + [\n'
            '        FieldPanel("intro"),\n'
            '        FieldPanel("body"),\n'
            '    ]</code></pre>'
            '<h2>Key Advantages of Wagtail</h2>'
            '<ul>'
            '<li><strong>StreamField</strong>: Build rich, structured content blocks (mix code blocks, quotes, galleries, and text) without breaking page layout.</li>'
            '<li><strong>Responsive Image Renditions</strong>: Automatic focal point cropping and on-the-fly resizing with <code>image.get_rendition(\'fill-800x450\')</code>.</li>'
            '<li><strong>Drafts and Version Control</strong>: Review draft revisions, schedule future publish dates, and audit editorial modification history.</li>'
            '</ul>'
        ),
    },
    'what-is-rag': {
        'intro': 'Overcoming LLM knowledge limits with Retrieval-Augmented Generation',
        'body': (
            '<h2>The Motivation for RAG</h2>'
            '<p>RAG retrieves relevant documents first, then lets the LLM answer from those results — helping reduce hallucinations.</p>'
            '<p>Standard large language models suffer from fixed training cutoffs, lack private organizational knowledge, and occasionally invent '
            'unverifiable facts when uncertain. RAG bridges this gap by grounding responses in verified, retrieved source texts.</p>'
            '<h2>The 3-Step RAG Architecture</h2>'
            '<ol>'
            '<li><strong>Chunking &amp; Indexing</strong>: Source documents are parsed, split into manageable chunks (e.g., 500–800 characters with 100-character overlap), '
            'and converted into high-dimensional vector embeddings stored in a vector database.</li>'
            '<li><strong>Retrieval</strong>: When a user asks a question, the system searches the index using cosine similarity, BM25 keyword matching, or hybrid reranking '
            'to retrieve the top-k most relevant passages.</li>'
            '<li><strong>Augmentation &amp; Generation</strong>: The retrieved passages are injected into the LLM system prompt as verified context. '
            'The model synthesizes a coherent answer strictly quoting from the provided evidence.</li>'
            '</ol>'
            '<h2>Evaluating RAG Systems</h2>'
            '<p>Robust RAG systems are monitored using three fundamental metrics: <em>Context Relevance</em> (how clean the retrieved chunks are), '
            '<em>Groundedness / Faithfulness</em> (whether the answer is strictly substantiated by the context), and <em>Answer Relevance</em> (whether the user question was directly resolved).</p>'
        ),
    },
    'agent-tool-design': {
        'intro': 'Architectural principles for reliable and auditable AI agent tools',
        'body': (
            '<h2>Core Design Philosophy</h2>'
            '<p>Tools should have a single responsibility, clear inputs/outputs, and be auditable. The LLM orchestrates; tools provide facts and computation.</p>'
            '<p>In agentic AI systems, treating the language model as a reasoning engine rather than a knowledge store produces significantly more reliable, '
            'deterministic, and scalable outcomes.</p>'
            '<h2>Key Principles of Tool Engineering</h2>'
            '<ul>'
            '<li><strong>Single Responsibility Principle (SRP)</strong>: Each tool must accomplish one distinct task (e.g., <code>search_articles</code> vs <code>add_to_reading_list</code>). Avoid multifunctional "Swiss Army knife" tools that confuse model routing.</li>'
            '<li><strong>Explicit Schema and Types</strong>: Provide strict parameter types, validation rules, and comprehensive descriptions. The model relies entirely on tool parameter docstrings to infer when and how to call the function.</li>'
            '<li><strong>Idempotency and Side-Effect Safety</strong>: Read operations should be side-effect free. Destructive or state-altering actions (e.g., placing orders, sending emails, deleting data) should require human confirmation or explicit validation checkpoints.</li>'
            '<li><strong>Auditing and Tracing</strong>: Every tool execution, input parameter set, and return payload should be logged for observability, evaluation benchmarking, and error debugging.</li>'
            '</ul>'
            '<h2>The ReAct Pattern in Action</h2>'
            '<p>Modern agents utilize the ReAct (Reasoning + Acting) loop: the agent generates a thought, invokes a tool, observes the structured output, '
            'and repeats this cycle until the user objective is fully achieved.</p>'
        ),
    },
    'path-ml-getting-started': {
        'intro': 'Curated progressive roadmap for mastering applied machine learning',
        'body': (
            '<h2>Roadmap Overview</h2>'
            '<p>Suggested order: ML overview → gradient descent intuition → linear regression in practice.</p>'
            '<p>This learning path takes you from high-level conceptual understanding to practical model training with production Python tooling.</p>'
            '<h2>Phase 1: Conceptual Foundations</h2>'
            '<p>Begin by mastering the distinction between supervised and unsupervised learning paradigms. Understand classification vs regression tasks, '
            'and familiarize yourself with feature matrices and target vectors.</p>'
            '<h2>Phase 2: Mathematical and Optimization Intuition</h2>'
            '<p>Explore the loss surface. Understand how gradient descent navigates error landscapes and why hyperparameter tuning (such as learning rate selection) '
            'governs convergence stability.</p>'
            '<h2>Phase 3: Hands-on Modeling with Scikit-Learn</h2>'
            '<p>Implement linear regression models from scratch using real datasets. Practice splitting data into train/test sets, '
            'evaluating models using Mean Squared Error and R² scores, and applying regularization techniques.</p>'
        ),
    },
    'path-python-web': {
        'intro': 'Complete developer pathway from language syntax to enterprise web services',
        'body': (
            '<h2>Roadmap Overview</h2>'
            '<p>Suggested order: Python basics → Django project structure → Wagtail quick start → HTTP and REST.</p>'
            '<p>Follow this structured curriculum to build scalable, secure, and modern web applications backed by Python.</p>'
            '<h2>Stage 1: Core Python Syntax</h2>'
            '<p>Master variables, dynamic typing, control flow, functions, and module packaging. Write clean, idiomatic code adhering to PEP 8 standards.</p>'
            '<h2>Stage 2: Enterprise Django Framework</h2>'
            '<p>Learn the Model-View-Template (MVT) pattern, database migrations with PostgreSQL, URL dispatching, and secure user authentication.</p>'
            '<h2>Stage 3: Headless and Content Management with Wagtail</h2>'
            '<p>Extend Django with Wagtail\'s hierarchical page tree, StreamFields, and editorial workflow moderation.</p>'
            '<h2>Stage 4: Network Protocols and RESTful APIs</h2>'
            '<p>Master HTTP verbs, status codes, JSON serialization, and API security for decoupled modern web architectures.</p>'
        ),
    },
}


class Command(BaseCommand):
    help = 'Enrich the 12 core articles in Supabase with deep content while keeping eval facts intact.'

    def handle(self, *args, **options):
        updated_count = 0
        total_chunks = 0

        with transaction.atomic():
            for slug, data in ENRICHED_ARTICLES.items():
                try:
                    article = ArticlePage.objects.get(slug=slug)
                except ArticlePage.DoesNotExist:
                    self.stderr.write(self.style.WARNING(f'Article with slug "{slug}" not found, skipping.'))
                    continue

                article.intro = data['intro'][:80]
                article.body = data['body']
                article.save(update_fields=['intro', 'body'])

                # Rebuild retrieval chunks immediately
                chunks = index_article(article)
                total_chunks += chunks
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(f'Enriched: {article.title} -> {chunks} chunks'))

        self.stdout.write(
            self.style.SUCCESS(f'Successfully enriched {updated_count} core articles ({total_chunks} total chunks).')
        )
