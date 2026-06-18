package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/websocket/v2"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/joho/godotenv"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/redis/go-redis/v9"
)

// ── Config ──────────────────────────────────────────────────────────────────

type Config struct {
	Port          string
	RedisAddr     string
	MinioEndpoint string
	MinioAccess   string
	MinioSecret   string
	MinioBucket   string
	DatabaseURL   string
}

func loadConfig() Config {
	godotenv.Load("../.env")
	return Config{
		Port:          envOr("GO_PORT", "8080"),
		RedisAddr:     envOr("REDIS_ADDR", "localhost:6379"),
		MinioEndpoint: envOr("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccess:   envOr("MINIO_ACCESS_KEY", "minioadmin"),
		MinioSecret:   envOr("MINIO_SECRET_KEY", "minioadmin"),
		MinioBucket:   envOr("MINIO_BUCKET", "documents"),
		DatabaseURL:   envOr("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/ocr_parse?sslmode=disable"),
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// ── Global clients ──────────────────────────────────────────────────────────

var (
	rdb         *redis.Client
	minioClient *minio.Client
	db          *pgxpool.Pool
	cfg         Config
)

const streamName = "doc_jobs"

//go:embed openapi.json
var openapiSpec []byte

const swaggerHTML = `<!DOCTYPE html>
<html><head>
<title>OCR Parse API — Swagger</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head><body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url:"/docs/openapi.json",dom_id:"#swagger-ui",deepLinking:true})</script>
</body></html>`

// ── Main ────────────────────────────────────────────────────────────────────

func main() {
	cfg = loadConfig()
	ctx := context.Background()

	// Redis
	rdb = redis.NewClient(&redis.Options{Addr: cfg.RedisAddr})
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Fatalf("Redis: %v", err)
	}
	log.Println("Redis connected")

	// MinIO
	var err error
	minioClient, err = minio.New(cfg.MinioEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinioAccess, cfg.MinioSecret, ""),
		Secure: false,
	})
	if err != nil {
		log.Fatalf("MinIO: %v", err)
	}
	if exists, _ := minioClient.BucketExists(ctx, cfg.MinioBucket); !exists {
		if err := minioClient.MakeBucket(ctx, cfg.MinioBucket, minio.MakeBucketOptions{}); err != nil {
			log.Fatalf("MinIO bucket: %v", err)
		}
	}
	log.Println("MinIO connected")

	// PostgreSQL
	db, err = pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("PostgreSQL: %v", err)
	}
	if err := db.Ping(ctx); err != nil {
		log.Fatalf("PostgreSQL ping: %v", err)
	}
	log.Println("PostgreSQL connected")

	// Fiber
	app := fiber.New(fiber.Config{
		BodyLimit: 20 * 1024 * 1024,
	})

	app.Use(logger.New(logger.Config{
		Format: "${time} ${status} ${method} ${path} ${latency}\n",
	}))
	app.Use(cors.New())

	// WebSocket upgrade middleware
	app.Use("/ws", func(c *fiber.Ctx) error {
		if websocket.IsWebSocketUpgrade(c) {
			return c.Next()
		}
		return fiber.ErrUpgradeRequired
	})

	// Swagger docs
	app.Get("/docs", func(c *fiber.Ctx) error {
		c.Set("Content-Type", "text/html")
		return c.SendString(swaggerHTML)
	})
	app.Get("/docs/openapi.json", func(c *fiber.Ctx) error {
		c.Set("Content-Type", "application/json")
		return c.Send(openapiSpec)
	})

	// Routes
	app.Post("/api/upload", handleUpload)
	app.Get("/api/jobs/:id", handleJobStatus)
	app.Get("/api/jobs/:id/result", handleJobResult)
	app.Get("/api/jobs", handleListJobs)
	app.Get("/ws/jobs/:id", websocket.New(handleJobWS))

	addr := fmt.Sprintf(":%s", cfg.Port)
	log.Printf("Gateway listening on %s", addr)
	log.Printf("Swagger docs → http://localhost:%s/docs", cfg.Port)
	log.Fatal(app.Listen(addr))
}

// ── Upload Handler ──────────────────────────────────────────────────────────

func handleUpload(c *fiber.Ctx) error {
	file, err := c.FormFile("file")
	if err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Tidak ada file dalam request"})
	}

	if file.Size > 20*1024*1024 {
		return c.Status(413).JSON(fiber.Map{"error": "File terlalu besar (maks 20 MB)"})
	}

	// Buka file
	src, err := file.Open()
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": "Gagal membuka file"})
	}
	defer src.Close()

	// Generate job ID dan file key
	jobID := uuid.New().String()
	fileKey := fmt.Sprintf("uploads/%s/%s", jobID, file.Filename)

	ctx := c.Context()

	// Upload ke MinIO
	_, err = minioClient.PutObject(ctx, cfg.MinioBucket, fileKey, src, file.Size, minio.PutObjectOptions{
		ContentType: file.Header.Get("Content-Type"),
	})
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": fmt.Sprintf("MinIO upload gagal: %v", err)})
	}

	// Simpan job ke PostgreSQL
	_, err = db.Exec(ctx,
		`INSERT INTO jobs (id, filename, file_key, file_size, status)
		 VALUES ($1, $2, $3, $4, 'queued')`,
		jobID, file.Filename, fileKey, file.Size,
	)
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": fmt.Sprintf("DB insert gagal: %v", err)})
	}

	// Push ke Redis Stream
	err = rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: streamName,
		Values: map[string]interface{}{
			"job_id":   jobID,
			"file_key": fileKey,
			"filename": file.Filename,
		},
	}).Err()
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": fmt.Sprintf("Redis stream gagal: %v", err)})
	}

	log.Printf("Job created: %s (%s, %d bytes)", jobID, file.Filename, file.Size)

	return c.Status(201).JSON(fiber.Map{
		"job_id":   jobID,
		"filename": file.Filename,
		"status":   "queued",
		"ws_url":   fmt.Sprintf("/ws/jobs/%s", jobID),
	})
}

// ── Job Status ──────────────────────────────────────────────────────────────

type JobRow struct {
	ID          string      `json:"id"`
	Filename    string      `json:"filename"`
	FileSize    int64       `json:"file_size"`
	Status      string      `json:"status"`
	CurrentStep *string     `json:"current_step"`
	Error       *string     `json:"error"`
	ElapsedMs   *int        `json:"elapsed_ms"`
	CreatedAt   time.Time   `json:"created_at"`
	UpdatedAt   time.Time   `json:"updated_at"`
	CompletedAt *time.Time  `json:"completed_at"`
}

func handleJobStatus(c *fiber.Ctx) error {
	jobID := c.Params("id")

	var job JobRow
	err := db.QueryRow(c.Context(),
		`SELECT id, filename, file_size, status, current_step, error,
		        elapsed_ms, created_at, updated_at, completed_at
		 FROM jobs WHERE id = $1`, jobID,
	).Scan(
		&job.ID, &job.Filename, &job.FileSize, &job.Status,
		&job.CurrentStep, &job.Error, &job.ElapsedMs,
		&job.CreatedAt, &job.UpdatedAt, &job.CompletedAt,
	)
	if err != nil {
		return c.Status(404).JSON(fiber.Map{"error": "Job tidak ditemukan"})
	}

	return c.JSON(job)
}

// ── Job Result ──────────────────────────────────────────────────────────────

func handleJobResult(c *fiber.Ctx) error {
	jobID := c.Params("id")

	var status string
	var result json.RawMessage

	err := db.QueryRow(c.Context(),
		"SELECT status, result FROM jobs WHERE id = $1", jobID,
	).Scan(&status, &result)
	if err != nil {
		return c.Status(404).JSON(fiber.Map{"error": "Job tidak ditemukan"})
	}
	if status != "completed" {
		return c.Status(202).JSON(fiber.Map{
			"status":  status,
			"message": "Job belum selesai",
		})
	}

	c.Set("Content-Type", "application/json")
	return c.Send(result)
}

// ── List Jobs ───────────────────────────────────────────────────────────────

func handleListJobs(c *fiber.Ctx) error {
	rows, err := db.Query(c.Context(),
		`SELECT id, filename, file_size, status, current_step, elapsed_ms, created_at
		 FROM jobs ORDER BY created_at DESC LIMIT 50`,
	)
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": "DB query gagal"})
	}
	defer rows.Close()

	type JobSummary struct {
		ID          string    `json:"id"`
		Filename    string    `json:"filename"`
		FileSize    int64     `json:"file_size"`
		Status      string    `json:"status"`
		CurrentStep *string   `json:"current_step"`
		ElapsedMs   *int      `json:"elapsed_ms"`
		CreatedAt   time.Time `json:"created_at"`
	}

	jobs := make([]JobSummary, 0)
	for rows.Next() {
		var j JobSummary
		if err := rows.Scan(&j.ID, &j.Filename, &j.FileSize, &j.Status, &j.CurrentStep, &j.ElapsedMs, &j.CreatedAt); err != nil {
			continue
		}
		jobs = append(jobs, j)
	}

	return c.JSON(fiber.Map{"jobs": jobs, "count": len(jobs)})
}

// ── WebSocket ───────────────────────────────────────────────────────────────

func handleJobWS(c *websocket.Conn) {
	jobID := c.Params("id")
	ctx := context.Background()

	channel := fmt.Sprintf("job:%s:status", jobID)
	sub := rdb.Subscribe(ctx, channel)
	defer sub.Close()

	ch := sub.Channel()

	// Kirim status awal dari DB
	var status, currentStep string
	var errStr *string
	row := db.QueryRow(ctx,
		"SELECT status, COALESCE(current_step, ''), error FROM jobs WHERE id = $1", jobID,
	)
	if err := row.Scan(&status, &currentStep, &errStr); err == nil {
		msg, _ := json.Marshal(fiber.Map{
			"job_id": jobID,
			"status": status,
			"step":   currentStep,
		})
		c.WriteMessage(websocket.TextMessage, msg)
	}

	// Forward Redis Pub/Sub → WebSocket
	for {
		select {
		case msg, ok := <-ch:
			if !ok {
				return
			}
			if err := c.WriteMessage(websocket.TextMessage, []byte(msg.Payload)); err != nil {
				return
			}
			// Tutup WebSocket jika job selesai atau gagal
			var parsed map[string]interface{}
			if json.Unmarshal([]byte(msg.Payload), &parsed) == nil {
				if s, ok := parsed["status"].(string); ok && (s == "completed" || s == "failed") {
					return
				}
			}
		}
	}
}
