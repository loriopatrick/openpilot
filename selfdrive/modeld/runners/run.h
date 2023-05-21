#pragma once

#include "runmodel.h"
#include "snpemodel.h"

#if defined(USE_THNEED)
#include "thneedmodel.h"
#include "bodythneedmodel.h"
#elif defined(USE_ONNX_MODEL)
#include "onnxmodel.h"
#endif
